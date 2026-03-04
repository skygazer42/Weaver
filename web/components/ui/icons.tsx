/**
 * Centralized icon system for Weaver.
 *
 * Uses **Phosphor Icons** — slightly warmer strokes and better visual weight
 * at small sizes (a better fit for our UI density).
 *
 * Components import from this module instead of a raw icon library,
 * ensuring a consistent aesthetic across the app.
 *
 * Usage:
 *   import { Globe, Code, Copy } from '@/components/ui/icons'
 *   <Globe className="h-4 w-4" />
 */

import * as React from 'react'
import type { Icon, IconProps, IconWeight } from '@phosphor-icons/react'
import {
  // Navigation & arrows
  ArrowDown as PhArrowDown,
  ArrowRight as PhArrowRight,
  ArrowUp as PhArrowUp,
  CaretDown,
  CaretLeft,
  CaretRight,
  CaretUp,
  List,
  SidebarSimple,

  // Layout
  SquaresFour,
  Compass,
  FolderOpen,
  ArrowsOut,
  ArrowsIn,
  Columns,
  House,

  // Actions
  Check,
  CheckCircle,
  ClipboardText,
  Copy,
  CursorClick,
  Download,
  ArrowSquareOut,
  Funnel,
  Link,
  Plus,
  ArrowCounterClockwise,
  ArrowClockwise,
  ArrowUUpLeft,
  Trash,

  // Communication & chat
  ChatText,

  // Content types
  ChartBar,
  BookOpen,
  BookmarkSimple,
  Brain,
  Code,
  Terminal,
  FileText,
  Image,
  ListChecks,
  Table,
  TextAlignLeft,

  // File
  File,

  // Status
  WarningCircle,
  Warning,
  CircleNotch,
  WifiSlash,
  XCircle,

  // Search & research
  Globe,
  MagnifyingGlass,
  Sparkle,
  TrendUp,

  // Mode & config
  Robot,
  Monitor,
  Plug,
  Rocket,
  Gear,
  Sliders,
  Wrench,
  GitBranch,

  // Edit & pen
  PencilLine,
  Pen,
  PenNib,

  // Audio & media
  Microphone,
  MicrophoneSlash,
  Play,
  Pause,
  Square,
  SpeakerHigh,
  SpeakerSlash,
  Camera,
  Waveform,

  // Theme
  Moon,
  Sun,

  // Pin/star
  Star as PhStar,

  // Close & cancel
  X,

  // Misc
  Bug,
  Clock,
  Eye,
  Lock,
  Paperclip,
  PaperPlaneRight,
  TestTube,
  TextAlignJustify,
  DotsThree,
  DotsThreeVertical,
  Circle,

  // History
  ClockCounterClockwise,

  // Share
  ShareNetwork,

  // Notepad
  Notebook,

  // Faders / sliders
  SlidersHorizontal,
} from '@phosphor-icons/react'

type MakeIconOptions = {
  defaultWeight?: IconWeight
  defaultProps?: Partial<IconProps>
}

function makeWeaverIcon(IconComponent: Icon, options: MakeIconOptions = {}): Icon {
  const defaultWeight: IconWeight = options.defaultWeight || 'regular'
  const defaultProps = options.defaultProps || {}
  const Wrapped = React.forwardRef<SVGSVGElement, IconProps>(({ weight, ...props }, ref) => {
    return (
      <IconComponent
        ref={ref}
        weight={weight || defaultWeight}
        {...defaultProps}
        {...props}
      />
    )
  })
  Wrapped.displayName = `WeaverIcon(${IconComponent.displayName || 'Icon'})`
  return Wrapped as unknown as Icon
}

// Navigation & arrows
export const ArrowDown = makeWeaverIcon(PhArrowDown)
export const ArrowRight = makeWeaverIcon(PhArrowRight)
export const ArrowUp = makeWeaverIcon(PhArrowUp)
export const ChevronDown = makeWeaverIcon(CaretDown)
export const ChevronLeft = makeWeaverIcon(CaretLeft)
export const ChevronRight = makeWeaverIcon(CaretRight)
export const ChevronUp = makeWeaverIcon(CaretUp)
export const Menu = makeWeaverIcon(List)
export const PanelRight = makeWeaverIcon(SidebarSimple, { defaultProps: { mirrored: true } })
export const PanelRightClose = makeWeaverIcon(SidebarSimple, { defaultProps: { mirrored: true } })
export const PanelRightOpen = makeWeaverIcon(SidebarSimple, { defaultProps: { mirrored: true } })
export const PanelLeftClose = makeWeaverIcon(SidebarSimple)
export const PanelLeftOpen = makeWeaverIcon(SidebarSimple)

// Layout & grid
export const LayoutGrid = makeWeaverIcon(SquaresFour)
export const Maximize2 = makeWeaverIcon(ArrowsOut)
export const Minimize2 = makeWeaverIcon(ArrowsIn)
export { Compass, FolderOpen, Columns }
export const Home = makeWeaverIcon(House)

// Actions
export const CheckCircle2 = makeWeaverIcon(CheckCircle)
export const ClipboardCopy = makeWeaverIcon(ClipboardText)
export const ExternalLink = makeWeaverIcon(ArrowSquareOut)
export const Filter = makeWeaverIcon(Funnel)
export const RefreshCcw = makeWeaverIcon(ArrowCounterClockwise)
export const RefreshCw = makeWeaverIcon(ArrowClockwise)
export const RotateCcw = makeWeaverIcon(ArrowUUpLeft)
export const Trash2 = makeWeaverIcon(Trash)
export { Check, Copy, CursorClick, Download, Link, Plus }

// Communication & chat
export const MessageSquare = makeWeaverIcon(ChatText)
export const MessageSquarePlus = makeWeaverIcon(ChatText)

// Content types
export const BarChart = makeWeaverIcon(ChartBar)
export const BarChart3 = makeWeaverIcon(ChartBar)
export const BookmarkPlus = makeWeaverIcon(BookmarkSimple)
export const Code2 = makeWeaverIcon(Terminal)
export const ImageIcon = makeWeaverIcon(Image)
export { BookOpen, Brain, Code, FileText, Image, ListChecks, Table, TextAlignLeft }

// File
export const FileIcon = makeWeaverIcon(File)
export { File }

// Status
export const AlertCircle = makeWeaverIcon(WarningCircle)
export const AlertTriangle = makeWeaverIcon(Warning)
export const Loader2 = makeWeaverIcon(CircleNotch)
export const WifiOff = makeWeaverIcon(WifiSlash)
export { XCircle }

// Search & research
export const Search = makeWeaverIcon(MagnifyingGlass)
export const Sparkles = makeWeaverIcon(Sparkle)
export const TrendingUp = makeWeaverIcon(TrendUp)
export { Globe }

// Mode & config
export const Bot = makeWeaverIcon(Robot)
export const Settings = makeWeaverIcon(Gear)
export const Settings2 = makeWeaverIcon(Sliders)
export { Monitor, Plug, Rocket, Wrench, GitBranch }

// Edit & pen
export const PenLine = makeWeaverIcon(Pen)
export const PenTool = makeWeaverIcon(PenNib)
export { PencilLine }

// Audio & media
export const Mic = makeWeaverIcon(Microphone)
export const MicOff = makeWeaverIcon(MicrophoneSlash)
export const Volume2 = makeWeaverIcon(SpeakerHigh)
export const VolumeX = makeWeaverIcon(SpeakerSlash)
export const AudioWaveform = makeWeaverIcon(Waveform)
export const AudioLines = makeWeaverIcon(Waveform)
export { Play, Pause, Square, Camera }

// Theme
export { Moon, Sun }

// Pin/star
export const Star = makeWeaverIcon(PhStar)
export const StarOff = makeWeaverIcon(PhStar, { defaultWeight: 'fill' })

// Close & cancel
export { X }

// Misc
export const Send = makeWeaverIcon(PaperPlaneRight)
export const WrapText = makeWeaverIcon(TextAlignJustify)
export const MoreHorizontal = makeWeaverIcon(DotsThree)
export const MoreVertical = makeWeaverIcon(DotsThreeVertical)
export { Bug, Clock, Eye, Lock, Paperclip, TestTube, Circle }

// History
export const History = makeWeaverIcon(ClockCounterClockwise)

// Share
export const Share = makeWeaverIcon(ShareNetwork)

// Notepad
export const Notepad = makeWeaverIcon(Notebook)

// Faders / sliders
export const Faders = makeWeaverIcon(SlidersHorizontal)
