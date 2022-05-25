const fs = require('fs');
const path = require('path');
const Git = require("nodegit");

const workdir = '/tmp';
const biocontainers = 'https://github.com/BioContainers/containers.git';
const bioconda = 'https://github.com/bioconda/bioconda-recipes.git';

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

async function repoFiles(kind='biocontainers') {
    let destDir = `${workdir}/${kind}`;
    let lastCommit = null;
    if (fs.existsSync(destDir)) {
        let existingRepo = await Git.Repository.open(destDir);
        let bc = await existingRepo.getBranchCommit('master');
        lastCommit = bc.sha();
        console.log('existing, last commit', lastCommit);
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
    if(lastCommit && lastCommit == headCommit) {
        console.log('nothing to do');
        return [];
    }
    if(lastCommit) {
        console.log('get diff');
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
    console.log('take all');
    let allFiles = getRepoFiles(destDir);
    for(let i=0;i<allFiles.length;i++) {
        allFiles[i] = allFiles[i].replace(destDir + '/', '');
    }
    return allFiles;
}

repoFiles('biocontainers').then(files => {
    console.log('files', files.length, files[0]);
    process.exit(0);
}).catch(err => {
    console.error(err);
    process.exit(1);
})