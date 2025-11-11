import React, { useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { CloudArrowUpIcon, DocumentIcon, FilmIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useVideo } from '../context/VideoContext'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const UploadSection = () => {
  const { addToQueue, processQueue, uploadQueue, clearQueue, isLoading } = useVideo()
  const [currentPair, setCurrentPair] = useState({ video: null, presentation: null })

  const videoDropzone = useDropzone({
    accept: {
      'video/*': ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    },
    maxFiles: 1,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        setCurrentPair(prev => ({ ...prev, video: acceptedFiles[0] }))
        toast.success('Video selected')
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
        {/* Video Upload */}
        <div className="card p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
            <FilmIcon className="h-5 w-5 mr-2 text-primary-600" />
            Video File
          </h3>
          
          <div
            {...videoDropzone.getRootProps()}
            className={clsx(
              'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors',
              videoDropzone.isDragActive
                ? 'border-primary-500 bg-primary-50'
                : 'border-gray-300 hover:border-gray-400'
            )}
          >
            <input {...videoDropzone.getInputProps()} />
            
            {currentPair.video ? (
              <div className="space-y-2">
                <FilmIcon className="h-12 w-12 mx-auto text-primary-600" />
                <p className="text-sm font-medium text-gray-900">{currentPair.video.name}</p>
                <p className="text-xs text-gray-500">{formatFileSize(currentPair.video.size)}</p>
              </div>
            ) : (
              <div className="space-y-2">
                <CloudArrowUpIcon className="h-12 w-12 mx-auto text-gray-400" />
                <p className="text-sm text-gray-600">
                  Drag & drop your video here, or click to select
                </p>
                <p className="text-xs text-gray-500">
                  Supported: MP4, AVI, MOV, MKV, WebM
                </p>
              </div>
            )}
          </div>
          
          {currentPair.video && (
            <button
              onClick={() => setCurrentPair(prev => ({ ...prev, video: null }))}
              className="mt-2 text-sm text-red-600 hover:text-red-700"
            >
              Remove video
            </button>
          )}
        </div>

        {/* Presentation Upload */}
        <div className="card p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
            <DocumentIcon className="h-5 w-5 mr-2 text-primary-600" />
            Presentation File
          </h3>
          
          <div
            {...presentationDropzone.getRootProps()}
            className={clsx(
              'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors',
              presentationDropzone.isDragActive
                ? 'border-primary-500 bg-primary-50'
                : 'border-gray-300 hover:border-gray-400'
            )}
          >
            <input {...presentationDropzone.getInputProps()} />
            
            {currentPair.presentation ? (
              <div className="space-y-2">
                <DocumentIcon className="h-12 w-12 mx-auto text-primary-600" />
                <p className="text-sm font-medium text-gray-900">{currentPair.presentation.name}</p>
                <p className="text-xs text-gray-500">{formatFileSize(currentPair.presentation.size)}</p>
              </div>
            ) : (
              <div className="space-y-2">
                <CloudArrowUpIcon className="h-12 w-12 mx-auto text-gray-400" />
                <p className="text-sm text-gray-600">
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
              className="mt-2 text-sm text-red-600 hover:text-red-700"
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
          <div className="p-4 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium text-gray-900">
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
          
          <div className="divide-y divide-gray-200">
            {uploadQueue.map((item) => (
              <div key={item.id} className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{item.video.name}</p>
                    <p className="text-xs text-gray-500">with {item.presentation.name}</p>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className={clsx(
                      'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
                      {
                        'bg-gray-100 text-gray-800': item.status === 'pending',
                        'bg-blue-100 text-blue-800': item.status === 'uploading',
                        'bg-green-100 text-green-800': item.status === 'completed',
                        'bg-red-100 text-red-800': item.status === 'failed'
                      }
                    )}>
                      {item.status}
                    </span>
                    {item.status === 'pending' && (
                      <button
                        onClick={() => {
                          // Remove from queue
                          // This would be implemented in the context
                        }}
                        className="text-gray-400 hover:text-gray-500"
                      >
                        <XMarkIcon className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
                {item.error && (
                  <p className="mt-1 text-xs text-red-600">{item.error}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default UploadSection
