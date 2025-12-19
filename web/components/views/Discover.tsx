'use client'

import React from 'react'
import { Compass, Sparkles, TrendingUp, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function Discover() {
  const featured = [
    { title: 'Market Trends 2025', desc: 'Deep dive into emerging tech markets', icon: TrendingUp, color: 'text-blue-500' },
    { title: 'Academic Research', desc: 'Find latest papers on LLM agents', icon: Search, color: 'text-purple-500' },
    { title: 'Creative Writing', desc: 'Story brainstorming with AI', icon: Sparkles, color: 'text-amber-500' },
  ]

  return (
    <div className="flex-1 h-full overflow-y-auto p-6 md:p-10">
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Compass className="h-8 w-8 text-primary" />
            Discover
          </h1>
          <p className="text-muted-foreground mt-2 text-lg">
            Explore curated research templates and community prompts.
          </p>
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search templates..." className="pl-10 h-12 text-base rounded-xl" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {featured.map((item, i) => (
            <div key={i} className="group p-6 rounded-2xl border bg-card hover:bg-muted/50 transition-all cursor-pointer shadow-sm hover:shadow-md">
              <div className={`h-12 w-12 rounded-xl bg-muted flex items-center justify-center mb-4 ${item.color} bg-opacity-10`}>
                <item.icon className={`h-6 w-6 ${item.color}`} />
              </div>
              <h3 className="font-semibold text-lg group-hover:text-primary transition-colors">{item.title}</h3>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
