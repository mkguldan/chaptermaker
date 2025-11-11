import React, { useState } from 'react'
import { Toaster } from 'react-hot-toast'
import Header from './components/Header'
import UploadSection from './components/UploadSection'
import JobsSection from './components/JobsSection'
import { VideoProvider } from './context/VideoContext'

function App() {
  const [activeTab, setActiveTab] = useState('upload')

  return (
    <VideoProvider>
      <div className="min-h-screen bg-gray-50">
        <Toaster position="top-right" />
        
        <Header />
        
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Tab Navigation */}
          <div className="border-b border-gray-200 mb-8">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setActiveTab('upload')}
                className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === 'upload'
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Upload & Process
              </button>
              <button
                onClick={() => setActiveTab('jobs')}
                className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === 'jobs'
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Processing Jobs
              </button>
            </nav>
          </div>
          
          {/* Tab Content */}
          <div>
            {activeTab === 'upload' && <UploadSection />}
            {activeTab === 'jobs' && <JobsSection />}
          </div>
        </main>
        
        <footer className="mt-auto py-6 text-center text-sm text-gray-500">
          <p>© 2025 Video Chapter Maker. Powered by OpenAI GPT-4o & GPT-5.</p>
        </footer>
      </div>
    </VideoProvider>
  )
}

export default App
