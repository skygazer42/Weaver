'use client'

import { useState, useEffect } from 'react'
import { Artifact } from '@/types/chat'
import { StorageService } from '@/lib/storage-service'

export function useArtifacts() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const loadArtifacts = () => {
      try {
        const saved = StorageService.getArtifacts<Artifact>()
        setArtifacts(saved.sort((a, b) => b.createdAt - a.createdAt))
      } catch (e) {
        console.error('Failed to load artifacts', e)
      } finally {
        setIsLoading(false)
      }
    }
    loadArtifacts()
  }, [])

  useEffect(() => {
    if (!isLoading) {
      StorageService.saveArtifacts(artifacts)
    }
  }, [artifacts, isLoading])

  const saveArtifact = (artifact: Omit<Artifact, 'id' | 'createdAt' | 'updatedAt'>) => {
    const now = Date.now()
    const newArtifact: Artifact = {
      ...artifact,
      id: now.toString() + Math.random().toString(36).substring(7),
      createdAt: now,
      updatedAt: now,
      tags: artifact.tags || []
    }
    setArtifacts(prev => [newArtifact, ...prev])
    return newArtifact
  }

  const deleteArtifact = (id: string) => {
    setArtifacts(prev => prev.filter(a => a.id !== id))
  }

  const updateArtifact = (id: string, updates: Partial<Artifact>) => {
    setArtifacts(prev => prev.map(a =>
      a.id === id ? { ...a, ...updates, updatedAt: Date.now() } : a
    ))
  }

  return {
    artifacts,
    isLoading,
    saveArtifact,
    deleteArtifact,
    updateArtifact
  }
}
