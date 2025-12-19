import { ImageAttachment } from '@/types/chat'

// Optimized for UI preview (instant, low memory)
export const createFilePreview = (file: File): { url: string; revoke: () => void } => {
    const url = URL.createObjectURL(file)
    return {
        url,
        revoke: () => URL.revokeObjectURL(url)
    }
}

// Optimized for API payload (Base64)
export const filesToImageAttachments = async (files: File[]): Promise<ImageAttachment[]> => {
  const convert = (file: File) => new Promise<ImageAttachment>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      const base64 = result && result.includes(',') ? result.split(',')[1] : result
      const mime = file.type || 'image/png'
      resolve({
        name: file.name,
        mime,
        data: base64,
        // We don't need the huge data: URI for preview if we are just sending data
        // But for consistency with the type definition, we might keep it or leave it empty if the UI doesn't use it after send
        preview: '' 
      })
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
  return Promise.all(files.map(convert))
}