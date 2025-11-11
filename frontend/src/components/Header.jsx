import React from 'react'
import { FilmIcon, SparklesIcon } from '@heroicons/react/24/outline'

const Header = () => {
  return (
    <header className="bg-gray-800 shadow-lg border-b border-gray-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center">
            <FilmIcon className="h-8 w-8 text-blue-400 mr-3" />
            <div>
              <h1 className="text-xl font-bold text-gray-100">Video Chapter Maker</h1>
              <p className="text-xs text-gray-400 flex items-center">
                <SparklesIcon className="h-3 w-3 mr-1" />
                Powered by GPT-4o & GPT-5
              </p>
            </div>
          </div>
          
          <div className="flex items-center space-x-4">
            <a
              href="/api/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-gray-400 hover:text-gray-300"
            >
              API Docs
            </a>
          </div>
        </div>
      </div>
    </header>
  )
}

export default Header
