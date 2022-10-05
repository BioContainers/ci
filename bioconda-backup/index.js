const axios = require('axios')
const AWS = require('aws-sdk');
const fs = require("fs");
const path = require("path");
const Git = require("nodegit");
const { execSync } = require("child_process");
const yaml_config = require('node-yaml-config');
const nodemailer = require('nodemailer');
const yargs = require("yargs");
const { fileURLToPath } = require('url');
const { PromisePool } = require('@supercharge/promise-pool');
const { json } = require('express');

const biocontainers = 'https://github.com/BioContainers/containers.git';
const bioconda = 'https://github.com/bioconda/bioconda-recipes.git';

const cfgpath = process.env.CONFIG !== undefined ? process.env.CONFIG : 'config.yml';

const config = yaml_config.load(cfgpath);

const s3 = new AWS.S3({
  endpoint: config.s3.endpoint,
  accessKeyId: config.s3.access_key,
  secretAccessKey: config.s3.secret_access_key,
  s3BucketEndpoint: true
});
const registry = config.registry.host

var docker_errors = 0;
var quay_errors = 0;
var last_login = 0;
var total = 0
// var errors = []

const getRepoFiles = function(dirPath, arrayOfFiles) {
    let files = fs.readdirSync(dirPath)
    arrayOfFiles = arrayOfFiles || []
  
    files.forEach(function(file) {
        if (fs.statSync(dirPath + "/" + file).isDirectory()) {
            arrayOfFiles = getRepoFiles(dirPath + "/" + file, arrayOfFiles)
        } else {
            let dirElt = dirPath.split('/');
            if(file == 'Dockerfile' || (file == 'meta.yaml' && dirElt[dirElt.length-2] == 'recipes')) {
            arrayOfFiles.push(path.join(dirPath, "/", file))
            }
        }
    })
  
    return arrayOfFiles
}

function save_tags(container, tags, kind) {
  if(!fs.existsSync(config.meta.path)) {
    console.debug('meta path does not exists, skipping save_tags')
    return
  }
  let dest = `${config.meta.path}/${container}_tags.json`
  let data = {
      name: container,
      docker: [],
      bioconda: []
  }
  if(fs.existsSync(dest)) {
      data = JSON.parse(fs.readFileSync(dest, 'utf-8'));
  }
  if (kind == 'docker') {
      tags.forEach(t => {
          if(data.docker.indexOf(t)<0) {
              data.docker.push(t)
          }
      });
  } else if (kind == 'bioconda') {
      tags.forEach(t => {
          if(data.bioconda.indexOf(t)<0) {
              data.bioconda.push(t)
          }
      });
  }
  if(data.docker.length>0 || data.bioconda.length>0) {
    fs.writeFileSync(dest, JSON.stringify(data))
  }

}

async function send_report() {
  console.log(`[report] total containers: ${total}, docker errors: ${docker_errors}, quay errors: ${quay_errors}`);
  if(!config.mail.smtp) {
    console.log('no mail configured, skipping report');
    return;
  }
  let transporter = nodemailer.createTransport({
    host: config.mail.smtp,
    port: 25,
    secure: false
  });

  let now = Date.now();
  
  let mailOptions = {
    from: config.mail.from,
    to: config.mail.to,
    subject: `[biocontainers][${now.toString()}] sync report`,
    text: `Sync: total=${total}, errors: docker=${docker_errors}, quay=${quay_errors}`
  };
  
  await transporter.sendMail(mailOptions);

}

async function repoFiles(kind='biocontainers', do_scan=false) {
    let destDir = `${config.workdir}/${kind}`;
    let lastCommit = null;
    if (fs.existsSync(destDir)) {
        let existingRepo = await Git.Repository.open(destDir);
        let bc = await existingRepo.getBranchCommit('master');
        lastCommit = bc.sha();
        console.log('existing, last commit', kind, lastCommit);
        fs.rmdirSync(destDir, {recursive: true, force: true})
        //fs.rmSync(destDir, {recursive: true});
    } 
    let repoUrl = kind == 'biocontainers' ? biocontainers : bioconda;
    await Git.Clone(repoUrl, destDir);
    let repo = await Git.Repository.open(destDir);
    let headc = await repo.getBranchCommit('master');
    let headCommit = headc.sha();
    console.log('last commit', lastCommit);
    console.log('head commit', headCommit);
    
    let files = [];
    if(!do_scan && lastCommit && lastCommit == headCommit) {
        console.log('nothing to do');
        return [];
    }
    if(!do_scan && lastCommit) {
        console.debug('get diff');
        let cold = await repo.getCommit(lastCommit);
        let coldTree = await cold.getTree();
        let cnew = await repo.getCommit(headCommit);
        let cnewTree = await cnew.getTree();
        const diff = await cnewTree.diff(coldTree);
        const patches = await diff.patches();
        
        for (const patch of patches) {
            files.push(patch.newFile().path());
        }
        // remove duplicates
        let uniqFiles = [...new Set(files)]
        return uniqFiles;

    }
    console.debug('take all');
    let allFiles = getRepoFiles(destDir);
    for(let i=0;i<allFiles.length;i++) {
        allFiles[i] = allFiles[i].replace(destDir + '/', '');
    }
    return allFiles;
}


async function getQuayioTags(container, scan_options) {
  let tags = [];
  let baseurl = `https://quay.io/api/v1/repository/biocontainers/${container}/tag/`;
  let page=1;
  let url = `${baseurl}?page=${page}`;
  while(true) {
    console.debug('call', url)
    try {
      let res = await axios.get(url);
      if(res.data.tags.length == 0) {
        return tags;
      }
      res.data.tags.forEach(tag => {
        tags.push(tag.name);
      });
    } catch(err) {
      if(err.response.status != 404) {
        quay_errors++;
        console.error('[quayio][tags] error', err.response.status, err.response.statusText);
      }
      save_tags(container, tags, 'bioconda');
      return tags;
    }
    page++;
    url = `${baseurl}?page=${page}`;
  }
}
async function getDockerhubTags(container, scan_options) {
  console.log('[docker][tags]', container);
  let tags = [];
  let url = `https://hub.docker.com/v2/repositories/biocontainers/${container}/tags`;
  while(true) {
    console.debug('call', url)
    try {
      let res = await axios.get(url);
      res.data.results.forEach(tag => {
        tags.push(tag.name);
      });
      if(!res.data.next || res.data.results.length == 0) {
        break;
      }
      url = res.data.next;
    } catch(err) {
      console.error('[dockerhub][tags] error', err.response.status, err.response.statusText);
      docker_errors++;
      break;
    }
  }
  save_tags(container, tags, 'docker');
  return tags;
}

async function getLocalBackupTag(container, tag) {
  // http://biocontainers.novalocal:5000/v2/biocontainers/abeona/manifests/0.23.0--py36_0
  let url = `http://${registry}/v2/biocontainers/${container}/manifests/${tag}`;
    console.debug('[local] call manifest', url)
    try {
      await axios.get(url);
      return true 
      
    } catch(err) {
      console.error('[local][tag] tag not found');
      return false
    }
}

async function backup(container, tag, quay, scan_options){
    let localBackup = false;
    // start a backup
    let fromContainer = `biocontainers/${container}:${tag}`;
    if(quay){
      fromContainer = `quay.io/biocontainers/${container}:${tag}`;
    }

    let isError = false;

    let toContainer = `${registry}/biocontainers/${container}:${tag}`;
    if(scan_options.backup) {
      try {
        // manifest on local registry does not work...
        // execSync(`docker manifest inspect ${toContainer}`);
        let exists = await getLocalBackupTag(container, tag)
        if(exists) {
          console.debug(`[backup][local] skip ${fromContainer} to ${toContainer}`);
        } else {
          localBackup = true;
          console.debug(`[backup][local] backup ${fromContainer} to ${toContainer}`);
        }
      } catch(err) {
        localBackup = true;
        console.debug(`[backup][local] backup ${fromContainer} to ${toContainer}`);
      }
    }

    let awsContainer = `public.ecr.aws/${config.aws}/${container}:${tag}`;
    let awsBackup = false;
    if(scan_options.aws) {
      if(!config.aws) {
        throw new Error(`[backup][aws] aws not configured ${container}:${tag}`)
      }
      try {
        let ts = Date.now()
        console.debug(`[aws][docker][login][last=${(new Date(last_login)).toLocaleString()}][now=${(new Date(ts)).toLocaleString()}]`)
        if(last_login === 0 || (last_login + (3600*1000)) < Date.now()) {
          console.debug('[backup][aws] run docker login', (new Date(ts)).toLocaleString());
          execSync('aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws');
          last_login = ts
        } else {
          console.log('[aws][login] no need to login')
        }

        execSync(`docker manifest inspect ${awsContainer}`);
        console.debug(`[backup][aws] skip ${awsContainer}`);
      } catch(err) {
        awsBackup = true;
        console.debug(`[backup][aws] backup ${awsContainer}`);
      }
    }

    let doBackup = localBackup || awsBackup;

    if(doBackup) {
      try {
        console.debug('[backup] run '+`docker pull ${fromContainer}`);
        if(!scan_options.dry) {
          execSync(`docker pull ${fromContainer}`);
        }
      } catch(err) {
        console.error(`[backup] failed to pull ${fromContainer}`);
        throw new Error(`[backup] ${container}:${tag}`)
      }
    }

    if(localBackup) {
      try {
        if(!scan_options.dry) {
          console.debug('[backup] run '+`docker tag ${fromContainer} ${toContainer}`);
          execSync(`docker tag ${fromContainer} ${toContainer}`);
          console.debug('[backup] run '+`docker push ${toContainer}`);
          execSync(`docker push ${toContainer}`);
        } else {
          console.log(`[backup][local] should tag and push ${fromContainer} ${toContainer}`)
        }
      } catch(err) {
        console.error('[backup] local backup error', err);
        isError = true;
      }

      try {
        console.debug('[backup] run '+`docker rmi ${toContainer}`);
        execSync(`docker rmi ${toContainer}`);
      } catch(err) {
        console.error(`[backup] delete error ${toContainer}`, err);
      }
    }

    // if aws, docker login and docker tag+push
    if(awsBackup) {
      if(!scan_options.dry) {
        try {
          console.debug('[backup][aws] create repo', container);
          execSync(`aws ecr-public create-repository --repository-name ${container}`);
        } catch(err) {
          console.debug(`[backup] aws repo creation failed, fine, may already exists `, err.message);
        }

        try {
          execSync(`docker tag ${fromContainer} ${awsContainer}`);
          console.debug(`[backup][aws] push ${awsContainer}`);
          execSync(`docker push ${awsContainer}`);
        } catch(err) {
          let ts = Date.now()
          console.error(`[backup] aws backup error ${awsContainer}`, err, (new Date(ts)).toLocaleString());
          isError = true;
        }
      } else {
        console.log(`[backup][aws] should tag and push ${fromContainer} ${awsContainer}`)
      }

      try {
        console.debug('[backup] run '+`docker rmi ${awsContainer}`);
        execSync(`docker rmi ${awsContainer}`);
      } catch(err) {
        console.error(`[backup] delete error ${awsContainer}`, err);
      }
    }


    if(doBackup && !scan_options.dry) {
      try {
        console.debug('[backup] run '+`docker rmi ${fromContainer}`);
        execSync(`docker rmi ${fromContainer}`);
      } catch(err) {
        console.error('[backup] cleanup error', err);
      }
    }

    if(isError) {
      throw new Error(`[backup] ${container}:${tag}`)
    }
}

async function getScanReport(container, tag, quay=false){
  console.debug('[scan][report]', container, tag);
  let prefix = '';
  if(quay) {
    prefix = 'quay.io/';
  }
  let url = `${config.anchore.url}/images`;
  let params = {
    fulltag: `${prefix}biocontainers/${container}:${tag}`,
    history: false
  }
  let res = null;
  let addImage = false;
  try {
    res = await axios.get(url, { params: params, auth:{
      username: config.anchore.user,
      password: config.anchore.password
    } });
    if(!res.data) {  
      addImage = true;
    } else {
      let digest = res.data[0].imageDigest;
      let vulnUrl = `${config.anchore.url}/images/${digest}/vuln/all`;
      res = await axios.get(vulnUrl,{
        auth:{
          username: config.anchore.user,
          password: config.anchore.password
        }
      });
    }

  } catch(err) {
    console.log('[scan] not found, add image', container, tag, err.response.status, err.response.statusText);
    addImage = true;
  }

  if(addImage) {
    console.log('[scan] add image', container, tag);
    let conn = ` --u ${config.anchore.user} --p ${config.anchore.password} --url ${config.anchore.url} `
    execSync(`anchore-cli ${conn} image add ${params.fulltag}`);
    return;
  }

  console.log('[scan] download and record', container, tag);
  let s3params = {Bucket: config.s3.bucket, Key: `${config.s3.bucket}/anchore/${container}/${tag}/anchore.json`, Body: JSON.stringify(res.data), ContentType: 'application/json'};
  try {
    await s3upload(s3params);
  } catch(err) {
    console.log('[scan] record error', container, tag, err);
  }
}

function s3upload(s3params) {
  return new Promise((resolve, reject) => {
    s3.upload(s3params, function(err, data) {
      if(err){
        console.error('[scan] upload error', err);
        reject(err);
        return;
      }
      console.debug('[scan][s3][upload] data', data);
      resolve(data);
    });
  })
}

async function doTheStuff(container, tag, quay, scan_options) {
  let ts = (new Date()).toLocaleString()
  console.log(`[doTheStuff][quay=${quay}][${ts}] ${container}:${tag}`)
  let is_error = false
  try {
    if(scan_options.security) {
      if(!scan_options.dry) {
        await getScanReport(container, tag, quay);
      } else {
        console.log('[security] should scan for report', container, tag)
      }
    }
  } catch(err) {
    is_error = true
    console.error('[docker] error', container, err.message)
    // errors.push(`[docker][security] ${container}: ${err.message}`)
  }
  try {    
    if(scan_options.backup || scan_options.aws) {
      await backup(container, tag, quay, scan_options);
    }
  } catch(err) {
    is_error = true
    console.error('[docker] error', container, err.message)
    // errors.push(`[docker][backup] ${container}: ${err.message}`)
  }
  if (is_error) {
    docker_errors++;
  }
  return {container, tag}
}

async function dockerhub(containers, scan_options) {
  console.log('[docker]', containers.length);
  let container_list = []
  for(let i=0;i<containers.length;i++) {
    let c = containers[i].name;
    if(c === undefined || c === null) {
      continue;
    }
    let tags = containers[i].tags;
    try {
      console.log('[docker]', c);
      if(!tags || tags.length==0) {
        tags = await getDockerhubTags(c, scan_options);
        await fs.writeFileSync(`${config.workdir}/biocontainers.json`, JSON.stringify({name: c, tags: tags, type: 'docker'}) + "\n", {flag: 'a+'});
      }
    } catch(err) {
      docker_errors++;
      console.error('[docker] error', c, err)
      continue
    }
    if(tags.length == 0){
      console.log('[docker] no tag found', c);
    }
    for(let t=0;t<tags.length;t++) {
      container_list.push({container: c, tag: tags[t], quay: false})

    }
  }
  return container_list
}

async function quayio(containers, scan_options) {
  console.log('[quay.io]', containers.length);
  let container_list = []
  for(let i=0;i<containers.length;i++) {
    let c = containers[i].name;
    if(c === undefined || c === null) {
      continue;
    }
    console.log('[quay.io]', c);
    let tags = containers[i].tags;
    try {
      if(!tags || tags.length==0) {
        tags = await getQuayioTags(c, scan_options);
        await fs.writeFileSync(`${config.workdir}/biocontainers.json`, JSON.stringify({name: c, tags: tags, type: 'bioconda'})+"\n", {flag: 'a+'});
      }
    } catch(err) {
      quay_errors++;
      console.error('[quay.io] error', c, err)
      continue
    }
    if(tags.length == 0){
      console.log('[quay.io] no tag found', c);
    }
    for(let t=0;t<tags.length;t++) {
      container_list.push({container: c, tag: tags[t], quay: true})
    }
  }
  return container_list
}

function scan(kind, scan_options) {
  if(kind == 'biocontainers' && !scan_options.docker) {
    return []
  }
  if(kind == 'bioconda' && !scan_options.conda) {
    return []
  }
  return repoFiles(kind, !scan_options.updated)
}

// let dockerhubImages = [];
// let quayioImages = [];

const options = yargs
 .usage('$0 <cmd> [args]')
 .option("a", { alias: "aws", describe: "Backup containers to AWS registry", type: "boolean"})
 .option("b", { alias: "backup", describe: "Backup containers to internal registry", type: "boolean"})
 .option("s", { alias: "security", describe: "Security scan updates", type: "boolean"})
 .option("u", { alias: "updated", describe: "Scan only updated containers/tags, else scan all", type: "boolean"})
 .options("c", {alias: "conda", describe: "check bioconda", type: "boolean"})
 .options("g", {alias: "docker", describe: "check biocontainers dockerfiles", type: "boolean"})
 .options("n", {alias: "use", describe: "use specific container for example bioconda:xxx or biocontainers:xxx"})
 .option("d", { alias: "dry", describe: "dry run, do not execute", type: "boolean"})
 .option("f", { alias: "file", describe: "file path to containers/tags list"})
 .argv;


async function getContainers(scan_options) {
  if(scan_options.use){
    let elt = scan_options.use.split(':')
    let c = [{'name': elt[1], 'tags': [], quay: elt[0] == 'biocontainers' ? false : true}]
    if(elt[0] == 'biocontainers') {
      return dockerhub(c, false)
    }
    return quayio(c, true)
  }
  if(scan_options.file) {
    let containers_file = fs.readFileSync(scan_options.file, 'UTF-8');
    let file_data = containers_file.split(/\r?\n/)
    let file_containers = []
    for(let i=0;i<file_data.length;i++){
      if(!file_data[i]){
        continue
      }
      let c = JSON.parse(file_data[i])
      for(let t=0;t<c.tags.length;t++) {
        // file lines: {name: c, tags: tags, type: 'docker'}
        // expected {container: container_name, tag: tag_name, quay: true|galse}
        file_containers.push({container: c.name, tag: c.tags[t], quay: c.type == 'bioconda' ? true : false})
      }
    }
    return file_containers
  }
  let containers = []
  let dockerfiles = await scan('biocontainers', scan_options)
  let docker_containers = []
  for(let i=0;i<dockerfiles.length;i++){
    let elts = dockerfiles[i].split('/');
    docker_containers.push({'name': elts[elts.length-3], 'tags': [], quay: false})
  }
  let data = await dockerhub(docker_containers, scan_options)
  containers = containers.concat(data)

  let condafiles = await scan('bioconda', scan_options)
  let conda_containers = []
  for(let i=0;i<condafiles.length;i++){
    let elts = condafiles[i].split('/');
    conda_containers.push({'name': elts[elts.length-2], 'tags': [], quay: true});
  }
  data = await quayio(conda_containers, scan_options)
  containers = containers.concat(data)

  return containers
  
}


if(fs.existsSync(`${config.workdir}/sync.lock`)) {
  console.error('Process is already running (sync.lock), exiting....')
  process.exit(1)
} else {
  fs.writeFileSync(`${config.workdir}/sync.lock`, '')
}

if(fs.existsSync(`${config.workdir}/biocontainers.json`)) {
  fs.unlinkSync(`${config.workdir}/biocontainers.json`);
}



getContainers(options).then((containers) => {
  let ts = new Date()
  console.log(`[containers][list][date=${ts.toLocaleString()}] ${containers.length} to handle!`)
  total = containers.length

  return PromisePool
  .for(containers)
  .withConcurrency(5)
  .process(async (container, index) => {
    console.log(`[process][${index}] ${container.container}:${container.tag}`)
    await doTheStuff(container.container, container.tag, container.quay, options)
  })
}).then((res) => {
  console.log('[doTheStuff]', res.results, res.errors)
  // cleanup
  try {
    execSync(`docker image prune -a`);
    console.debug('[cleanup] done');
  } catch(err) {
    console.error('[cleanup] failed');
  }
  return send_report()
}).then(() => {
  console.log('done', total, docker_errors, quay_errors);
  fs.unlinkSync(`${config.workdir}/sync.lock`);
  process.exit(0);
}).catch(err => {
  console.error('oopps!', err, docker_errors, quay_errors);
  fs.unlinkSync(`${config.workdir}/sync.lock`);
  process.exit(1);
})


