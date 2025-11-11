import React from 'react'
import { Toaster } from 'react-hot-toast'
import Header from './components/Header'
import UploadSection from './components/UploadSection'
import JobsSection from './components/JobsSection'
import { VideoProvider } from './context/VideoContext'

function App() {
  return (
    <VideoProvider>
      <div className="min-h-screen bg-gray-900">
        <Toaster position="top-right" />
        
        <Header />
        
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-8">
            {/* Upload Section */}
            <UploadSection />
            
            {/* Jobs Section */}
            <JobsSection />
          </div>
        </main>
        
        <footer className="mt-auto py-6 text-center text-sm text-gray-400">
          <p>© 2025 Video Chapter Maker. Powered by OpenAI GPT-4o & GPT-5.</p>
        </footer>
      </div>
    </VideoProvider>
  )
}

export default App
