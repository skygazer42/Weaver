/**
 * Centralized icon system for Weaver.
 *
 * Uses Phosphor Icons with the **Duotone** weight by default.
 * Components import from this module instead of a raw icon library,
 * ensuring a consistent, premium aesthetic across the app.
 *
 * Usage:
 *   import { Globe, Code, Copy } from '@/components/ui/icons'
 *   <Globe className="h-4 w-4" />
 */

import type { ComponentProps, FC } from 'react'

// ---- Phosphor imports (tree-shaken) ----
import {
  ArrowDown as PArrowDown,
  ArrowRight as PArrowRight,
  ArrowUp as PArrowUp,
  ArrowsOutSimple as PArrowsOutSimple,
  ArrowsInSimple as PArrowsInSimple,
  BookBookmark as PBookBookmark,
  BookOpen as PBookOpen,
  Brain as PBrain,
  Bug as PBug,
  Camera as PCamera,
  CaretDown as PCaretDown,
  CaretLeft as PCaretLeft,
  CaretRight as PCaretRight,
  CaretUp as PCaretUp,
  ChartBar as PChartBar,
  ChatCircle as PChatCircle,
  ChatCircleDots as PChatCircleDots,
  Check as PCheck,
  CheckCircle as PCheckCircle,
  Clipboard as PClipboard,
  ClockCounterClockwise as PClockCounterClockwise,
  Clock as PClock,
  Code as PCode,
  Compass as PCompass,
  Copy as PCopy,
  CursorClick as PCursorClick,
  DownloadSimple as PDownloadSimple,
  Eye as PEye,
  ArrowSquareOut as PArrowSquareOut,
  File as PFile,
  FileText as PFileText,
  Faders as PFaders,
  Funnel as PFunnel,
  FolderOpen as PFolderOpen,
  Gear as PGear,
  GearSix as PGearSix,
  GitBranch as PGitBranch,
  GlobeHemisphereWest as PGlobe,
  GridFour as PGridFour,
  House as PHouse,
  Image as PImage,
  Link as PLink,
  List as PList,
  ListChecks as PListChecks,
  Lock as PLock,
  MagnifyingGlass as PMagnifyingGlass,
  Microphone as PMicrophone,
  MicrophoneSlash as PMicrophoneSlash,
  Monitor as PMonitor,
  Moon as PMoon,
  Notepad as PNotepad,
  PaperclipHorizontal as PPaperclip,
  PaperPlaneTilt as PPaperPlane,
  Pause as PPause,
  PencilSimpleLine as PPencilLine,
  PenNib as PPenNib,
  Play as PPlay,
  Plug as PPlug,
  Plus as PPlus,
  Robot as PRobot,
  Rocket as PRocket,
  SidebarSimple as PSidebarSimple,
  SpinnerGap as PSpinnerGap,
  Sparkle as PSparkle,
  SpeakerHigh as PSpeakerHigh,
  SpeakerSlash as PSpeakerSlash,
  Star as PStar,
  Stop as PStop,
  Sun as PSun,
  Table as PTable,
  Terminal as PTerminal,
  TestTube as PTestTube,
  TextAlignLeft as PTextAlignLeft,
  TextIndent as PTextIndent,
  Trash as PTrash,
  TrendUp as PTrendUp,
  Warning as PWarning,
  WarningCircle as PWarningCircle,
  WifiSlash as PWifiSlash,
  Wrench as PWrench,
  X as PX,
  XCircle as PXCircle,
  DotsThree as PDotsThree,
  DotsThreeVertical as PDotsThreeVertical,
  Columns as PColumns,
  ShareNetwork as PShareNetwork,
} from '@phosphor-icons/react'

// ---- Default props applied to every icon ----
type PhosphorIconType = FC<ComponentProps<typeof PCheck>>
type IconWeight = 'thin' | 'light' | 'regular' | 'bold' | 'fill' | 'duotone'

const DEFAULT_WEIGHT: IconWeight = 'duotone'

/**
 * Wrap a Phosphor icon component so `weight` defaults to "duotone".
 * The caller can still override via props.
 */
function wrap(Icon: PhosphorIconType): PhosphorIconType {
  const Wrapped: PhosphorIconType = (props) => (
    <Icon weight={DEFAULT_WEIGHT} {...(props as any)} />
  )
  Wrapped.displayName = Icon.displayName
  return Wrapped
}

// ---- Exported icon components ----
// Names match (or alias) the lucide-react names used throughout Weaver.
// This lets us migrate imports with a simple path change.

// Navigation & Arrows
export const ArrowDown = wrap(PArrowDown)
export const ArrowRight = wrap(PArrowRight)
export const ArrowUp = wrap(PArrowUp)
export const ChevronDown = wrap(PCaretDown)
export const ChevronLeft = wrap(PCaretLeft)
export const ChevronRight = wrap(PCaretRight)
export const ChevronUp = wrap(PCaretUp)
export const Menu = wrap(PList)
export const PanelRight = wrap(PSidebarSimple)
export const PanelRightClose = wrap(PSidebarSimple)
export const PanelRightOpen = wrap(PSidebarSimple)
export const PanelLeftClose = wrap(PSidebarSimple)
export const PanelLeftOpen = wrap(PSidebarSimple)

// Layout & Grid
export const LayoutGrid = wrap(PGridFour)
export const Compass = wrap(PCompass)
export const FolderOpen = wrap(PFolderOpen)
export const Maximize2 = wrap(PArrowsOutSimple)
export const Minimize2 = wrap(PArrowsInSimple)
export const Columns = wrap(PColumns)
export const Home = wrap(PHouse)

// Actions
export const Check = wrap(PCheck)
export const CheckCircle2 = wrap(PCheckCircle)
export const ClipboardCopy = wrap(PClipboard)
export const Copy = wrap(PCopy)
export const CursorClick = wrap(PCursorClick)
export const Download = wrap(PDownloadSimple)
export const ExternalLink = wrap(PArrowSquareOut)
export const Filter = wrap(PFunnel)
export const Link = wrap(PLink)
export const Plus = wrap(PPlus)
export const RefreshCcw = wrap(PClockCounterClockwise)
export const RefreshCw = wrap(PClockCounterClockwise)
export const RotateCcw = wrap(PClockCounterClockwise)
export const Trash2 = wrap(PTrash)

// Communication & Chat
export const MessageSquare = wrap(PChatCircle)
export const MessageSquarePlus = wrap(PChatCircleDots)

// Content Types
export const BarChart = wrap(PChartBar)
export const BarChart3 = wrap(PChartBar)
export const BookOpen = wrap(PBookOpen)
export const BookmarkPlus = wrap(PBookBookmark)
export const Brain = wrap(PBrain)
export const Code = wrap(PCode)
export const Code2 = wrap(PTerminal)
export const FileText = wrap(PFileText)
export const Image = wrap(PImage)
export const ImageIcon = wrap(PImage)
export const ListChecks = wrap(PListChecks)
export const Table = wrap(PTable)
export const TextAlignLeft = wrap(PTextAlignLeft)

// File
export const File = wrap(PFile)
export const FileIcon = wrap(PFile)

// Status
export const AlertCircle = wrap(PWarningCircle)
export const AlertTriangle = wrap(PWarning)
export const Loader2 = wrap(PSpinnerGap)
export const WifiOff = wrap(PWifiSlash)
export const XCircle = wrap(PXCircle)

// Search & Research
export const Globe = wrap(PGlobe)
export const Search = wrap(PMagnifyingGlass)
export const Sparkles = wrap(PSparkle)
export const TrendingUp = wrap(PTrendUp)

// Mode & Config
export const Bot = wrap(PRobot)
export const Monitor = wrap(PMonitor)
export const Plug = wrap(PPlug)
export const Rocket = wrap(PRocket)
export const Settings = wrap(PGear)
export const Settings2 = wrap(PGearSix)
export const Wrench = wrap(PWrench)
export const GitBranch = wrap(PGitBranch)

// Edit & Pen
export const PencilLine = wrap(PPencilLine)
export const PenLine = wrap(PPencilLine)
export const PenTool = wrap(PPenNib)

// Audio & Media
export const Mic = wrap(PMicrophone)
export const MicOff = wrap(PMicrophoneSlash)
export const Play = wrap(PPlay)
export const Pause = wrap(PPause)
export const Square = wrap(PStop)
export const Volume2 = wrap(PSpeakerHigh)
export const VolumeX = wrap(PSpeakerSlash)
export const Camera = wrap(PCamera)

// Theme
export const Moon = wrap(PMoon)
export const Sun = wrap(PSun)

// Pin/Star
export const Star = wrap(PStar)
export const StarOff = wrap(PStar)

// Close & Cancel
export const X = wrap(PX)

// Misc
export const Bug = wrap(PBug)
export const Clock = wrap(PClock)
export const Eye = wrap(PEye)
export const Lock = wrap(PLock)
export const Paperclip = wrap(PPaperclip)
export const Send = wrap(PPaperPlane)
export const TestTube = wrap(PTestTube)
export const WrapText = wrap(PTextIndent)
export const MoreHorizontal = wrap(PDotsThree)
export const MoreVertical = wrap(PDotsThreeVertical)
export const Circle = wrap(PCheck)

// History
export const History = wrap(PClockCounterClockwise)

// Share
export const Share = wrap(PShareNetwork)

// Notepad
export const Notepad = wrap(PNotepad)

// Faders
export const Faders = wrap(PFaders)
