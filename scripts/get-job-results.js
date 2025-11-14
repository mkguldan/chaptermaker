#!/usr/bin/env node

/**
 * Quick script to fetch job results and download URLs
 * Usage: node scripts/get-job-results.js <job_id>
 * Example: node scripts/get-job-results.js job_ea0e30a98257
 */

const https = require('https');

const API_BASE = 'https://chaptermaker-695406125250.europe-west1.run.app/api/v1';

function fetchJobResults(jobId) {
  return new Promise((resolve, reject) => {
    const url = `${API_BASE}/jobs/${jobId}/results`;
    
    console.log(`🔍 Fetching results for ${jobId}...`);
    console.log(`URL: ${url}\n`);
    
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
    console.error('❌ Error: Please provide a job ID');
    console.log('Usage: node scripts/get-job-results.js <job_id>');
    console.log('Example: node scripts/get-job-results.js job_ea0e30a98257');
    process.exit(1);
  }
  
  try {
    const results = await fetchJobResults(jobId);
    
    console.log('✅ Job Results:\n');
    console.log(`Status: ${results.status}`);
    console.log(`Job ID: ${results.job_id}\n`);
    
    if (results.statistics) {
      console.log('📊 Statistics:');
      Object.entries(results.statistics).forEach(([key, value]) => {
        console.log(`  ${key}: ${value}`);
      });
      console.log('');
    }
    
    console.log('📥 Download URLs:\n');
    Object.entries(results.download_urls).forEach(([name, url]) => {
      console.log(`${name}:`);
      console.log(`  ${url}\n`);
    });
    
    console.log('✅ Copy the URLs above to download your files!');
    
  } catch (error) {
    console.error(`❌ Error: ${error.message}`);
    process.exit(1);
  }
}

main();

