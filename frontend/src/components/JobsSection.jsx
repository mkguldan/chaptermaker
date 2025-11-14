import React, { useState, useEffect } from 'react'
import { useVideo } from '../context/VideoContext'
import { 
  ArrowDownTrayIcon, 
  CheckCircleIcon, 
  XCircleIcon,
  ClockIcon,
  ExclamationCircleIcon,
  ArrowPathIcon,
  FilmIcon
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const JobsSection = () => {
  const { jobs, getJobResults } = useVideo()

  const handleDownload = async (jobId, fileType) => {
    try {
      const results = await getJobResults(jobId)
      
      if (results.download_urls && results.download_urls[fileType]) {
        window.open(results.download_urls[fileType], '_blank')
        toast.success(`Downloading ${fileType}`)
      } else {
        toast.error(`${fileType} not available`)
      }
    } catch (error) {
      toast.error(`Failed to download ${fileType}`)
    }
  }

  const handleDownloadAll = (jobId) => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const downloadAllUrl = `${apiUrl}/api/v1/jobs/${jobId}/download-all`
      window.location.href = downloadAllUrl
      toast.success('Downloading all files...')
    } catch (error) {
      toast.error('Failed to download all files')
    }
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-500" />
      case 'processing':
        return <ArrowPathIcon className="h-5 w-5 text-blue-500 animate-spin" />
      case 'pending':
        return <ClockIcon className="h-5 w-5 text-gray-400" />
      case 'cancelled':
        return <ExclamationCircleIcon className="h-5 w-5 text-yellow-500" />
      default:
        return null
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed':
        return 'bg-green-500/20 text-green-400'
      case 'failed':
        return 'bg-red-500/20 text-red-400'
      case 'processing':
        return 'bg-blue-500/20 text-blue-400'
      case 'pending':
        return 'bg-gray-500/20 text-gray-400'
      case 'cancelled':
        return 'bg-yellow-500/20 text-yellow-400'
      default:
        return 'bg-gray-500/20 text-gray-400'
    }
  }

  const formatDate = (dateString) => {
    const date = new Date(dateString)
    return date.toLocaleString()
  }

  const getVideoName = (path) => {
    if (!path) return 'Unknown'
    return path.split('/').pop()
  }

  if (jobs.length === 0) {
    return null
  }
  
  console.log('Rendering jobs:', jobs)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-gray-100">Processing Jobs</h2>
        <div className="text-sm text-gray-400">
          {jobs.filter(j => j.status === 'processing').length} active • {jobs.filter(j => j.status === 'completed').length} completed
        </div>
      </div>

      {jobs.map((job) => (
        <div key={job.job_id} className="card">
          <div className="p-6">
            <div className="flex items-start justify-between">
              <div className="flex items-start space-x-3">
                {getStatusIcon(job.status)}
                <div>
                  <h4 className="text-base font-medium text-gray-100">
                    {getVideoName(job.video_path || job.presentation_path)}
                  </h4>
                  <p className="text-xs text-gray-500 mt-1">
                    Job ID: {job.job_id || 'N/A'}
                  </p>
                  {job.created_at && (
                    <p className="text-xs text-gray-500">
                      Created: {formatDate(job.created_at)}
                    </p>
                  )}
                </div>
              </div>
              
              <span className={clsx(
                'inline-flex items-center px-3 py-1 rounded-full text-xs font-medium',
                getStatusColor(job.status)
              )}>
                {job.status}
              </span>
            </div>

            {/* Progress Bar */}
            {job.status === 'processing' && job.progress !== undefined && (
              <div className="mt-4">
                <div className="flex items-center justify-between text-xs text-gray-400 mb-2">
                  <span>{job.message || 'Processing...'}</span>
                  <span>{job.progress}%</span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div 
                    className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${job.progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Error Message */}
            {job.error && (
              <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-md">
                <p className="text-sm text-red-400">{job.error}</p>
              </div>
            )}
            
            {/* Download Buttons */}
            {job.status === 'completed' && (
              <div className="mt-4 pt-4 border-t border-gray-700">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm text-gray-400">Download Results:</p>
                  
                  {/* Download All Button */}
                  <button
                    onClick={() => handleDownloadAll(job.job_id)}
                    className="inline-flex items-center px-4 py-2 bg-gradient-to-r from-pink-500/20 to-purple-500/20 hover:from-pink-500/30 hover:to-purple-500/30 text-pink-400 rounded-md text-sm font-semibold transition-colors border border-pink-500/30"
                  >
                    <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                    Download All
                  </button>
                </div>
                
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => handleDownload(job.job_id, 'chapters')}
                    className="inline-flex items-center px-4 py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 rounded-md text-sm font-medium transition-colors"
                  >
                    <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                    Chapters CSV
                  </button>
                  
                  <button
                    onClick={() => handleDownload(job.job_id, 'subtitles')}
                    className="inline-flex items-center px-4 py-2 bg-green-500/20 hover:bg-green-500/30 text-green-400 rounded-md text-sm font-medium transition-colors"
                  >
                    <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                    Subtitles SRT
                  </button>
                  
                  <button
                    onClick={() => handleDownload(job.job_id, 'transcript')}
                    className="inline-flex items-center px-4 py-2 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 rounded-md text-sm font-medium transition-colors"
                  >
                    <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                    Transcript TXT
                  </button>
                  
                  <button
                    onClick={() => handleDownload(job.job_id, 'slides')}
                    className="inline-flex items-center px-4 py-2 bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 rounded-md text-sm font-medium transition-colors"
                  >
                    <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                    Slides (jpg.zip)
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      ))}
    </div>
  )
}

export default JobsSection
