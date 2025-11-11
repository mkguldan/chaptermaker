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
  const { jobs, getJobStatus, getJobResults, pollJobStatus } = useVideo()
  const [localJobs, setLocalJobs] = useState([])
  const [expandedJob, setExpandedJob] = useState(null)

  useEffect(() => {
    // Initialize local jobs from context
    setLocalJobs(jobs)
  }, [jobs])

  useEffect(() => {
    // Set up polling for active jobs
    const cleanupFunctions = []
    
    localJobs.forEach(job => {
      if (job.status === 'processing' || job.status === 'pending') {
        const cleanup = pollJobStatus(job.job_id, (updatedJob) => {
          setLocalJobs(prev => 
            prev.map(j => j.job_id === updatedJob.job_id ? updatedJob : j)
          )
        })
        cleanupFunctions.push(cleanup)
      }
    })

    return () => {
      cleanupFunctions.forEach(cleanup => cleanup())
    }
  }, [localJobs, pollJobStatus])

  const handleDownloadResults = async (jobId) => {
    try {
      const results = await getJobResults(jobId)
      
      // Open download links in new tabs
      if (results.download_urls) {
        Object.entries(results.download_urls).forEach(([key, url]) => {
          window.open(url, '_blank')
        })
        toast.success('Downloads started')
      }
    } catch (error) {
      toast.error('Failed to get download links')
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
        return 'bg-green-100 text-green-800'
      case 'failed':
        return 'bg-red-100 text-red-800'
      case 'processing':
        return 'bg-blue-100 text-blue-800'
      case 'pending':
        return 'bg-gray-100 text-gray-800'
      case 'cancelled':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const formatDate = (dateString) => {
    const date = new Date(dateString)
    return date.toLocaleString()
  }

  const getVideoName = (path) => {
    return path.split('/').pop()
  }

  if (localJobs.length === 0) {
    return (
      <div className="text-center py-12">
        <FilmIcon className="h-12 w-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">No processing jobs yet</h3>
        <p className="text-gray-500">Upload videos to start processing</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium text-gray-900">Processing Jobs</h2>
        <div className="text-sm text-gray-500">
          {localJobs.filter(j => j.status === 'processing').length} active jobs
        </div>
      </div>

      {localJobs.map((job) => (
        <div key={job.job_id} className="card">
          <div className="p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start space-x-3">
                {getStatusIcon(job.status)}
                <div>
                  <h4 className="text-sm font-medium text-gray-900">
                    {getVideoName(job.video_path)}
                  </h4>
                  <p className="text-xs text-gray-500 mt-1">
                    Job ID: {job.job_id}
                  </p>
                  <p className="text-xs text-gray-500">
                    Created: {formatDate(job.created_at)}
                  </p>
                </div>
              </div>
              
              <div className="flex items-center space-x-2">
                <span className={clsx(
                  'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
                  getStatusColor(job.status)
                )}>
                  {job.status}
                </span>
                
                {job.status === 'completed' && (
                  <button
                    onClick={() => handleDownloadResults(job.job_id)}
                    className="p-1 text-gray-400 hover:text-gray-500"
                    title="Download results"
                  >
                    <ArrowDownTrayIcon className="h-5 w-5" />
                  </button>
                )}
              </div>
            </div>

            {/* Progress Bar */}
            {job.status === 'processing' && job.progress !== undefined && (
              <div className="mt-4">
                <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                  <span>{job.message || 'Processing...'}</span>
                  <span>{job.progress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div 
                    className="bg-primary-600 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${job.progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Error Message */}
            {job.error && (
              <div className="mt-3 p-3 bg-red-50 rounded-md">
                <p className="text-sm text-red-800">{job.error}</p>
              </div>
            )}

            {/* Expandable Details */}
            {job.status === 'completed' && (
              <button
                onClick={() => setExpandedJob(expandedJob === job.job_id ? null : job.job_id)}
                className="mt-3 text-sm text-primary-600 hover:text-primary-700"
              >
                {expandedJob === job.job_id ? 'Hide details' : 'Show details'}
              </button>
            )}

            {expandedJob === job.job_id && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <dl className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Video</dt>
                    <dd className="mt-1 text-sm text-gray-900">{getVideoName(job.video_path)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Presentation</dt>
                    <dd className="mt-1 text-sm text-gray-900">{getVideoName(job.presentation_path)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Started</dt>
                    <dd className="mt-1 text-sm text-gray-900">{formatDate(job.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Completed</dt>
                    <dd className="mt-1 text-sm text-gray-900">
                      {job.completed_at ? formatDate(job.completed_at) : '-'}
                    </dd>
                  </div>
                </dl>

                {job.metadata?.statistics && (
                  <div className="mt-4">
                    <h5 className="text-xs font-medium text-gray-500 mb-2">Statistics</h5>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
                      <div>
                        <dt className="text-xs text-gray-500">Duration</dt>
                        <dd className="text-sm font-medium text-gray-900">
                          {Math.round(job.metadata.statistics.duration_seconds / 60)} min
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-gray-500">Chapters</dt>
                        <dd className="text-sm font-medium text-gray-900">
                          {job.metadata.statistics.chapters_count}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-gray-500">Slides</dt>
                        <dd className="text-sm font-medium text-gray-900">
                          {job.metadata.statistics.slides_extracted}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-gray-500">Language</dt>
                        <dd className="text-sm font-medium text-gray-900 uppercase">
                          {job.metadata.statistics.language}
                        </dd>
                      </div>
                    </dl>
                  </div>
                )}

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    onClick={() => handleDownloadResults(job.job_id)}
                    className="btn-primary text-sm"
                  >
                    <ArrowDownTrayIcon className="h-4 w-4 mr-1" />
                    Download All Results
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
