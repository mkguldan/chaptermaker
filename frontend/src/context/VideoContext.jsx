import React, { createContext, useContext, useState, useCallback } from 'react'
import toast from 'react-hot-toast'
import api from '../services/api'

const VideoContext = createContext()

export const useVideo = () => {
  const context = useContext(VideoContext)
  if (!context) {
    throw new Error('useVideo must be used within a VideoProvider')
  }
  return context
}

export const VideoProvider = ({ children }) => {
  const [jobs, setJobs] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [uploadQueue, setUploadQueue] = useState([])
  const [uploadProgress, setUploadProgress] = useState({})

  // Get upload URL from backend
  const getUploadUrl = useCallback(async (filename) => {
    try {
      const response = await api.post('/videos/upload', null, {
        params: { filename }
      })
      return response.data
    } catch (error) {
      console.error('Error getting upload URL:', error)
      throw error
    }
  }, [])

  // Get presentation upload URL
  const getPresentationUploadUrl = useCallback(async (filename) => {
    try {
      const response = await api.post('/presentations/upload', null, {
        params: { filename }
      })
      return response.data
    } catch (error) {
      console.error('Error getting presentation upload URL:', error)
      throw error
    }
  }, [])

  // Upload file to GCS using signed URL with progress tracking
  const uploadToGCS = useCallback(async (file, uploadUrl, itemId) => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      
      // Track upload progress
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percentComplete = Math.round((e.loaded / e.total) * 100)
          const speed = e.loaded / ((Date.now() - startTime) / 1000) // bytes per second
          
          setUploadProgress(prev => ({
            ...prev,
            [itemId]: {
              progress: percentComplete,
              loaded: e.loaded,
              total: e.total,
              speed: speed
            }
          }))
        }
      })
      
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(true)
        } else {
          reject(new Error(`Upload failed with status ${xhr.status}: ${xhr.statusText}`))
        }
      })
      
      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'))
      })
      
      xhr.addEventListener('abort', () => {
        reject(new Error('Upload aborted'))
      })
      
      const startTime = Date.now()
      xhr.open('PUT', uploadUrl, true)
      xhr.setRequestHeader('Content-Type', file.type)
      xhr.send(file)
    })
  }, [])

  // Process single video
  const processVideo = useCallback(async (videoPath, presentationPath, options = {}) => {
    try {
      const response = await api.post('/videos/process', {
        video_path: videoPath,
        presentation_path: presentationPath,
        options
      })
      
      const newJob = response.data
      setJobs(prev => [newJob, ...prev])
      
      return newJob
    } catch (error) {
      console.error('Error processing video:', error)
      throw error
    }
  }, [])

  // Batch process videos
  const batchProcessVideos = useCallback(async (items) => {
    try {
      const response = await api.post('/videos/batch', { items })
      const newJobs = response.data
      
      setJobs(prev => [...newJobs, ...prev])
      
      return newJobs
    } catch (error) {
      console.error('Error batch processing:', error)
      throw error
    }
  }, [])

  // Get job status
  const getJobStatus = useCallback(async (jobId) => {
    try {
      const response = await api.get(`/jobs/${jobId}`)
      return response.data
    } catch (error) {
      console.error('Error getting job status:', error)
      throw error
    }
  }, [])

  // Get job results
  const getJobResults = useCallback(async (jobId) => {
    try {
      const response = await api.get(`/jobs/${jobId}/results`)
      return response.data
    } catch (error) {
      console.error('Error getting job results:', error)
      throw error
    }
  }, [])

  // Poll job status
  const pollJobStatus = useCallback(async (jobId, onUpdate) => {
    const interval = setInterval(async () => {
      try {
        const status = await getJobStatus(jobId)
        onUpdate(status)
        
        if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
          clearInterval(interval)
        }
      } catch (error) {
        console.error('Error polling job status:', error)
        clearInterval(interval)
      }
    }, 2000) // Poll every 2 seconds
    
    return () => clearInterval(interval)
  }, [getJobStatus])

  // Add to upload queue
  const addToQueue = useCallback((video, presentation) => {
    const queueItem = {
      id: Date.now().toString(),
      video,
      presentation,
      status: 'pending'
    }
    
    setUploadQueue(prev => [...prev, queueItem])
    return queueItem
  }, [])

  // Process upload queue
  const processQueue = useCallback(async () => {
    setIsLoading(true)
    const pendingItems = uploadQueue.filter(item => item.status === 'pending')
    
    for (const item of pendingItems) {
      try {
        // Update status
        setUploadQueue(prev => 
          prev.map(q => q.id === item.id ? { ...q, status: 'uploading_video' } : q)
        )
        
        // Upload video
        const videoUpload = await getUploadUrl(item.video.name)
        await uploadToGCS(item.video, videoUpload.upload_url, `${item.id}-video`)
        
        // Upload presentation
        setUploadQueue(prev => 
          prev.map(q => q.id === item.id ? { ...q, status: 'uploading_presentation' } : q)
        )
        const presentationUpload = await getPresentationUploadUrl(item.presentation.name)
        await uploadToGCS(item.presentation, presentationUpload.upload_url, `${item.id}-presentation`)
        
        // Process video
        setUploadQueue(prev => 
          prev.map(q => q.id === item.id ? { ...q, status: 'processing' } : q)
        )
        const job = await processVideo(
          videoUpload.file_path,
          presentationUpload.file_path
        )
        
        // Update status
        setUploadQueue(prev => 
          prev.map(q => q.id === item.id ? { ...q, status: 'completed', jobId: job.job_id } : q)
        )
        
        // Clear progress
        setUploadProgress(prev => {
          const newProgress = { ...prev }
          delete newProgress[`${item.id}-video`]
          delete newProgress[`${item.id}-presentation`]
          return newProgress
        })
        
        toast.success(`Started processing ${item.video.name}`)
        
      } catch (error) {
        console.error('Error processing queue item:', error)
        
        setUploadQueue(prev => 
          prev.map(q => q.id === item.id ? { ...q, status: 'failed', error: error.message } : q)
        )
        
        toast.error(`Failed to process ${item.video.name}: ${error.message}`)
      }
    }
    
    setIsLoading(false)
  }, [uploadQueue, getUploadUrl, getPresentationUploadUrl, uploadToGCS, processVideo])

  // Clear queue
  const clearQueue = useCallback(() => {
    setUploadQueue([])
  }, [])

  const value = {
    jobs,
    isLoading,
    uploadQueue,
    uploadProgress,
    getUploadUrl,
    getPresentationUploadUrl,
    uploadToGCS,
    processVideo,
    batchProcessVideos,
    getJobStatus,
    getJobResults,
    pollJobStatus,
    addToQueue,
    processQueue,
    clearQueue
  }

  return (
    <VideoContext.Provider value={value}>
      {children}
    </VideoContext.Provider>
  )
}

export default VideoContext
