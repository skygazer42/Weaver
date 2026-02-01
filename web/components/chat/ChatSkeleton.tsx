'use client'

import React from 'react'
import { LoadingSkeleton } from '@/components/ui/loading'

/**
 * Full chat page skeleton for initial load
 */
export function ChatSkeleton() {
  return (
    <div className="flex h-screen">
      {/* Sidebar skeleton */}
      <div className="w-64 border-r p-4 space-y-3 hidden md:block">
        <LoadingSkeleton className="h-10 w-full rounded-lg" />
        <div className="space-y-2 mt-4">
          {[1, 2, 3, 4, 5].map(i => (
            <LoadingSkeleton key={i} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      </div>

      {/* Main content skeleton */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <LoadingSkeleton className="h-14 w-full" />

        {/* Messages area */}
        <div className="flex-1 p-4 space-y-4">
          {/* User message */}
          <div className="flex justify-end">
            <LoadingSkeleton className="h-16 w-2/3 rounded-2xl" />
          </div>
          {/* Assistant message */}
          <div className="flex justify-start">
            <LoadingSkeleton className="h-24 w-3/4 rounded-2xl" />
          </div>
          {/* User message */}
          <div className="flex justify-end">
            <LoadingSkeleton className="h-12 w-1/2 rounded-2xl" />
          </div>
        </div>

        {/* Input area */}
        <div className="p-4">
          <LoadingSkeleton className="h-20 w-full max-w-5xl mx-auto rounded-3xl" />
        </div>
      </div>
    </div>
  )
}

/**
 * Message list skeleton
 */
export function MessagesSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-4 p-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={`flex ${i % 2 === 0 ? 'justify-end' : 'justify-start'}`}>
          <LoadingSkeleton
            className={`h-16 rounded-2xl ${i % 2 === 0 ? 'w-2/3' : 'w-3/4'}`}
          />
        </div>
      ))}
    </div>
  )
}

/**
 * Sidebar skeleton
 */
export function SidebarSkeleton() {
  return (
    <div className="w-64 border-r p-4 space-y-3">
      <LoadingSkeleton className="h-10 w-full rounded-lg" />
      <div className="space-y-2 mt-4">
        {[1, 2, 3, 4, 5, 6].map(i => (
          <LoadingSkeleton key={i} className="h-10 w-full rounded-lg" />
        ))}
      </div>
    </div>
  )
}

/**
 * Artifacts panel skeleton
 */
export function ArtifactsSkeleton() {
  return (
    <div className="w-[400px] border-l p-4 space-y-4">
      <LoadingSkeleton className="h-8 w-32 rounded-lg" />
      <div className="space-y-3">
        {[1, 2].map(i => (
          <div key={i} className="space-y-2">
            <LoadingSkeleton className="h-6 w-24 rounded" />
            <LoadingSkeleton className="h-48 w-full rounded-lg" />
          </div>
        ))}
      </div>
    </div>
  )
}
