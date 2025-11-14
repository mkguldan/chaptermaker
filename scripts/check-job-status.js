#!/usr/bin/env node

const https = require('https');

const API_BASE = 'https://chaptermaker-695406125250.europe-west1.run.app/api/v1';

function getJobStatus(jobId) {
  return new Promise((resolve, reject) => {
    const url = `${API_BASE}/jobs/${jobId}`;
    
    https.get(url, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        if (res.statusCode === 200) {
          resolve(JSON.parse(data));
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${data}`));
        }
      });
    }).on('error', reject);
  });
}

async function main() {
  const jobId = process.argv[2];
  
  if (!jobId) {
    console.error('Usage: node scripts/check-job-status.js <job_id>');
    process.exit(1);
  }
  
  try {
    const job = await getJobStatus(jobId);
    
    console.log('\n📊 Job Status:\n');
    console.log(`Job ID: ${job.job_id}`);
    console.log(`Status: ${job.status}`);
    console.log(`Created: ${job.created_at}`);
    console.log(`Updated: ${job.updated_at}`);
    
    if (job.message) {
      console.log(`\n💬 Message: ${job.message}`);
    }
    
    if (job.error) {
      console.log(`\n❌ Error:\n${job.error}`);
    }
    
    if (job.progress !== undefined) {
      console.log(`\nProgress: ${job.progress}%`);
    }
    
  } catch (error) {
    console.error(`❌ Error: ${error.message}`);
    process.exit(1);
  }
}

main();

