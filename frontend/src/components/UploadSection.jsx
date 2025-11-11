import React, { useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { CloudArrowUpIcon, DocumentIcon, FilmIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useVideo } from '../context/VideoContext'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const UploadSection = () => {
  const { addToQueue, processQueue, uploadQueue, clearQueue, isLoading, uploadProgress } = useVideo()
  const [currentPair, setCurrentPair] = useState({ video: null, presentation: null })
  
  const formatSpeed = (bytesPerSecond) => {
    if (!bytesPerSecond) return '0 MB/s'
    const mbps = bytesPerSecond / (1024 * 1024)
    return mbps.toFixed(2) + ' MB/s'
  }

  const videoDropzone = useDropzone({
    accept: {
      'video/*': ['.mp4', '.avi', '.mov', '.mkv', '.webm'],
      'audio/*': ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma']
    },
    maxFiles: 1,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        setCurrentPair(prev => ({ ...prev, video: acceptedFiles[0] }))
        const fileType = acceptedFiles[0].type.startsWith('audio/') ? 'Audio' : 'Video'
        toast.success(`${fileType} file selected`)
      }
    }
  })

  const presentationDropzone = useDropzone({
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.ms-powerpoint': ['.ppt'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx']
    },
    maxFiles: 1,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        setCurrentPair(prev => ({ ...prev, presentation: acceptedFiles[0] }))
        toast.success('Presentation selected')
      }
    }
  })

  const handleAddToQueue = () => {
    if (!currentPair.video || !currentPair.presentation) {
      toast.error('Please select both video and presentation files')
      return
    }

    addToQueue(currentPair.video, currentPair.presentation)
    setCurrentPair({ video: null, presentation: null })
    toast.success('Added to queue')
  }

  const handleProcessQueue = async () => {
    if (uploadQueue.length === 0) {
      toast.error('Queue is empty')
      return
    }

    await processQueue()
  }

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  return (
    <div className="space-y-8">
      {/* Upload Area */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Video/Audio Upload */}
        <div className="card p-6">
          <h3 className="text-lg font-medium text-gray-100 mb-4 flex items-center">
            <FilmIcon className="h-5 w-5 mr-2 text-blue-400" />
            Video or Audio File
          </h3>
          
          <div
            {...videoDropzone.getRootProps()}
            className={clsx(
              'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors',
              videoDropzone.isDragActive
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-600 hover:border-gray-500'
            )}
          >
            <input {...videoDropzone.getInputProps()} />
            
            {currentPair.video ? (
              <div className="space-y-2">
                <FilmIcon className="h-12 w-12 mx-auto text-blue-400" />
                <p className="text-sm font-medium text-gray-100">{currentPair.video.name}</p>
                <p className="text-xs text-gray-400">{formatFileSize(currentPair.video.size)}</p>
              </div>
            ) : (
              <div className="space-y-2">
                <CloudArrowUpIcon className="h-12 w-12 mx-auto text-gray-500" />
                <p className="text-sm text-gray-300">
                  Drag & drop your video or audio here, or click to select
                </p>
                <p className="text-xs text-gray-500">
                  Video: MP4, AVI, MOV, MKV, WebM
                </p>
                <p className="text-xs text-gray-500">
                  Audio: MP3, WAV, M4A, AAC, OGG, FLAC
                </p>
              </div>
            )}
          </div>
          
          {currentPair.video && (
            <button
              onClick={() => setCurrentPair(prev => ({ ...prev, video: null }))}
              className="mt-2 text-sm text-red-400 hover:text-red-300"
            >
              Remove file
            </button>
          )}
        </div>

        {/* Presentation Upload */}
        <div className="card p-6">
          <h3 className="text-lg font-medium text-gray-100 mb-4 flex items-center">
            <DocumentIcon className="h-5 w-5 mr-2 text-blue-400" />
            Presentation File
          </h3>
          
          <div
            {...presentationDropzone.getRootProps()}
            className={clsx(
              'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors',
              presentationDropzone.isDragActive
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-600 hover:border-gray-500'
            )}
          >
            <input {...presentationDropzone.getInputProps()} />
            
            {currentPair.presentation ? (
              <div className="space-y-2">
                <DocumentIcon className="h-12 w-12 mx-auto text-blue-400" />
                <p className="text-sm font-medium text-gray-100">{currentPair.presentation.name}</p>
                <p className="text-xs text-gray-400">{formatFileSize(currentPair.presentation.size)}</p>
              </div>
            ) : (
              <div className="space-y-2">
                <CloudArrowUpIcon className="h-12 w-12 mx-auto text-gray-500" />
                <p className="text-sm text-gray-300">
                  Drag & drop your presentation here, or click to select
                </p>
                <p className="text-xs text-gray-500">
                  Supported: PPT, PPTX, PDF
                </p>
              </div>
            )}
          </div>
          
          {currentPair.presentation && (
            <button
              onClick={() => setCurrentPair(prev => ({ ...prev, presentation: null }))}
              className="mt-2 text-sm text-red-400 hover:text-red-300"
            >
              Remove presentation
            </button>
          )}
        </div>
      </div>

      {/* Add to Queue Button */}
      <div className="flex justify-center">
        <button
          onClick={handleAddToQueue}
          disabled={!currentPair.video || !currentPair.presentation}
          className="btn-primary"
        >
          Add to Queue
        </button>
      </div>

      {/* Queue Section */}
      {uploadQueue.length > 0 && (
        <div className="card">
          <div className="p-4 border-b border-gray-700">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium text-gray-100">
                Upload Queue ({uploadQueue.filter(item => item.status === 'pending').length} pending)
              </h3>
              <div className="flex items-center space-x-2">
                <button
                  onClick={clearQueue}
                  className="btn-secondary text-sm"
                  disabled={isLoading}
                >
                  Clear Queue
                </button>
                <button
                  onClick={handleProcessQueue}
                  className="btn-primary text-sm"
                  disabled={isLoading || uploadQueue.filter(item => item.status === 'pending').length === 0}
                >
                  {isLoading ? 'Processing...' : 'Process All'}
                </button>
              </div>
            </div>
          </div>
          
          <div className="divide-y divide-gray-700">
            {uploadQueue.map((item) => {
              const videoProgress = uploadProgress[`${item.id}-video`]
              const presentationProgress = uploadProgress[`${item.id}-presentation`]
              const currentProgress = item.status === 'uploading_video' ? videoProgress : presentationProgress
              
              return (
                <div key={item.id} className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex-1 mr-4">
                      <p className="text-sm font-medium text-gray-100">{item.video.name}</p>
                      <p className="text-xs text-gray-400">with {item.presentation.name}</p>
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className={clsx(
                        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium whitespace-nowrap',
                        {
                          'bg-gray-700 text-gray-300': item.status === 'pending',
                          'bg-blue-600 text-blue-100': item.status.includes('uploading'),
                          'bg-yellow-600 text-yellow-100': item.status === 'processing',
                          'bg-green-600 text-green-100': item.status === 'completed',
                          'bg-red-600 text-red-100': item.status === 'failed'
                        }
                      )}>
                        {item.status === 'uploading_video' && 'Uploading Video'}
                        {item.status === 'uploading_presentation' && 'Uploading Slides'}
                        {item.status === 'processing' && 'Processing'}
                        {item.status === 'pending' && 'Pending'}
                        {item.status === 'completed' && 'Completed'}
                        {item.status === 'failed' && 'Failed'}
                      </span>
                      {item.status === 'pending' && (
                        <button
                          onClick={() => {
                            // Remove from queue
                            // This would be implemented in the context
                          }}
                          className="text-gray-500 hover:text-gray-400"
                        >
                          <XMarkIcon className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                  
                  {/* Progress Bar */}
                  {currentProgress && (
                    <div className="mt-2 space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-400">
                          {formatFileSize(currentProgress.loaded)} / {formatFileSize(currentProgress.total)}
                        </span>
                        <span className="text-gray-400">
                          {formatSpeed(currentProgress.speed)} • {currentProgress.progress}%
                        </span>
                      </div>
                      <div className="w-full bg-gray-700 rounded-full h-2">
                        <div
                          className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${currentProgress.progress}%` }}
                        />
                      </div>
                    </div>
                  )}
                  
                  {item.error && (
                    <p className="mt-2 text-xs text-red-400">{item.error}</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default UploadSection
