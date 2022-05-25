const axios = require('axios')
const AWS = require('aws-sdk');
const fs = require("fs");
const path = require("path");
const Git = require("nodegit");
const { execSync } = require("child_process");
const yaml_config = require('node-yaml-config');
const nodemailer = require('nodemailer');
const yargs = require("yargs");

const biocontainers = 'https://github.com/BioContainers/containers.git';
const bioconda = 'https://github.com/bioconda/bioconda-recipes.git';

var config = yaml_config.load('config.yml');

const s3 = new AWS.S3({
  endpoint: config.s3.endpoint,
  accessKeyId: config.s3.access_key,
  secretAccessKey: config.s3.secret_access_key,
  s3BucketEndpoint: true
});
const registry = config.registry.host

var docker_errors = 0;
var quay_errors = 0;

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
  let dest = `/${config.meta.path}/${container}_tags.json`
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
  console.log(`[report] total containers: ${$total}, docker errors: ${docker_errors}, quay errors: ${quay_errors}`);
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
  
  var mailOptions = {
    from: config.mail.from,
    to: config.mail.to,
    subject: `[biocontainers][${now.toString()}] sync report`,
    text: `Sync: total=${total}, errors: docker=${docker_errors}, quay=${quay_errors}`
  };
  
  await transporter.sendMail(mailOptions);

}

async function repoFiles(kind='biocontainers', scan=false) {
    let destDir = `${config.workdir}/${kind}`;
    let lastCommit = null;
    if (fs.existsSync(destDir)) {
        let existingRepo = await Git.Repository.open(destDir);
        let bc = await existingRepo.getBranchCommit('master');
        lastCommit = bc.sha();
        console.log('existing, last commit', kind, lastCommit);
        fs.rmSync(destDir, {recursive: true});
    } 
    let repoUrl = kind == 'biocontainers' ? biocontainers : bioconda;
    await Git.Clone(repoUrl, destDir);
    let repo = await Git.Repository.open(destDir);
    let headc = await repo.getBranchCommit('master');
    let headCommit = headc.sha();
    console.log('last commit', lastCommit);
    console.log('head commit', headCommit);
    
    let files = [];
    if(!scan && lastCommit && lastCommit == headCommit) {
        console.log('nothing to do');
        return [];
    }
    if(!scan && lastCommit) {
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
        return files;

    }
    console.debug('take all');
    let allFiles = getRepoFiles(destDir);
    for(let i=0;i<allFiles.length;i++) {
        allFiles[i] = allFiles[i].replace(destDir + '/', '');
    }
    return allFiles;
}


async function getQuayioTags(container) {
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
async function getDockerhubTags(container) {
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

async function backup(container, tag, quay=false){
    let localBackup = false;
    // start a backup
    let fromContainer = `biocontainers/${container}:${tag}`;
    if(quay){
      fromContainer = `quay.io/biocontainers/${container}:${tag}`;
    }

    let isError = false;

    let toContainer = `${registry}/biocontainers/${container}:${tag}`;
    try {
      execSync(`docker manifest inspect ${toContainer}`);
      console.debug(`[backup] skip ${fromContainer} to ${toContainer}`);
    } catch(err) {
      localBackup = true;
      console.debug(`[backup] backup ${fromContainer} to ${toContainer}`);
    }

    let awsContainer = `public.ecr.aws/${config.aws}/${container}:${tag}`;
    let awsBackup = false;
    if(config.aws) {
      try {
        execSync(`docker manifest inspect ${awsContainer}`);
        console.debug(`[backup] skip ${awsContainer}`);
      } catch(err) {
        awsBackup = true;
        console.debug(`[backup] backup ${awsContainer}`);
      }
    }

    let doBackup = localBackup || awsBackup;

    if(doBackup) {
      try {
      console.debug('[backup] run '+`docker pull ${fromContainer}`);
      execSync(`docker pull ${fromContainer}`);
      } catch(err) {
        console.error(`[backup] failed to pull ${fromContainer}`);
      }
    }

    if(localBackup) {
      try {
        console.debug('[backup] run '+`docker tag ${fromContainer} ${toContainer}`);
        execSync(`docker tag ${fromContainer} ${toContainer}`);
        console.debug('[backup] run '+`docker push ${toContainer}`);
        execSync(`docker push ${toContainer}`);
        console.debug('[backup] run '+`docker rmi ${toContainer}`);
        execSync(`docker rmi ${toContainer}`);
      } catch(err) {
        console.error('[backup] local backup error', err);
        isError = true;
      }
    }

    // if aws, docker login and docker tag+push
    if(awsBackup) {
        try {
          console.debug('[backup][aws] run docker login');
          execSync('aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws');
        } catch(err) {
          console.debug(`[backup] aws login error `, err);
          isError = true;
        }

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
          execSync('docker logout')
          console.debug('[backup] run '+`docker rmi ${awsContainer}`);
          execSync(`docker rmi ${awsContainer}`);
        } catch(err) {
          console.error(`[backup] aws backup error ${awsContainer}`, err);
          isError = true;
        }
    }


    if(doBackup) {
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
    console.log('[scan] not found, add image', err.response.status, err.response.statusText);
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
      console.debug('data', data);
      resolve(data);
    });
  })
}

async function dockerhub(containers, options) {
  console.log('[docker]', containers.length);
  for(let i=0;i<containers.length;i++) {
    let c = containers[i].name;
    if(c === undefined || c === null) {
      continue;
    }
    let tags = containers[i].tags;
    try {
      console.log('[docker]', c);
      if(!tags || tags.length==0) {
        tags = await getDockerhubTags(c);
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
      try {
        if(options.security) {
          await getScanReport(c, tags[t], false);
        }
        if(options.backup) {
          await backup(c, tags[t], false);
        }
      } catch(err) {
        docker_errors++;
        console.error('[docker] error', c, err.message)
      }
    }
  }
}

async function quayio(containers, options) {
  console.log('[quay.io]', containers.length);

  for(let i=0;i<containers.length;i++) {
    let c = containers[i].name;
    if(c === undefined || c === null) {
      continue;
    }
    console.log('[quay.io]', c);
    let tags = containers[i].tags;
    try {
      if(!tags || tags.length==0) {
        tags = await getQuayioTags(c);
        await fs.writeFileSync(`${config.workdir}/biocontainers.json`, JSON.stringify({name: c, tags: tags, type: 'bioconda'})+"\n", {flag: 'a+'});
      }
    } catch(err) {
      quay_errors++;
      console.error('[quay.io] error', c, err)
      continue
    }
    if(tags.length == 0){
      console.log('[docker] no tag found', c);
    }
    for(let t=0;t<tags.length;t++) {
      try {
        if(options.security) {
          await getScanReport(c, tags[t], true);
        }
        if(options.backup) {
          await backup(c, tags[t], true);
        }
      } catch(err) {
        quay_errors++;
        console.error('[quay.io] error', c, err.message)
      }
    }
  }
}


let dockerhubImages = [];
let quayioImages = [];
let total = 0;


const options = yargs
 .usage('$0 <cmd> [args]')
 .option("b", { alias: "backup", describe: "Backup containers", type: "boolean"})
 .option("s", { alias: "security", describe: "Security scan updates", type: "boolean"})
 .option("u", { alias: "updated", describe: "Scan only updated containers/tags, else scan all", type: "boolean"})
 .argv;

if(fs.existsSync(`${config.workdir}/biocontainers.json`)) {
  fs.unlinkSync(`${config.workdir}/biocontainers.json`);
}

// scan all to get up-to-date scan repo
repoFiles('biocontainers', !options.updated).then(dockerfiles => {
    for(let i=0;i<dockerfiles.length;i++){
        let elts = dockerfiles[i].split('/');
        dockerhubImages.push({'name': elts[elts.length-3], 'tags': []})
    }
    total += dockerhubImages.length;
    return dockerhubImages;
}).then((images) => {
      return dockerhub(images, options);
}).then(() => {
    return repoFiles('bioconda', !options.updated);
}).then(condafiles => {
    for(let i=0;i<condafiles.length;i++){
        let elts = condafiles[i].split('/');
        quayioImages.push({'name': elts[elts.length-2], 'tags': []});
    }
    total += quayioImages.length;
    return quayioImages;
}).then(images => {
    return quayio(images, options);
}).then(() => {
    return send_report();
}).then(() => {
    console.log('done', total, docker_errors, quay_errors);
    process.exit(0);
}).catch(err => {
    console.error('oopps!', err, docker_errors, quay_errors);
    process.exit(1);
})