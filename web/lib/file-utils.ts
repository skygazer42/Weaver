import { ImageAttachment } from '@/types/chat'

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
        preview: result?.startsWith('data:') ? result : `data:${mime};base64,${base64}`
      })
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
  return Promise.all(files.map(convert))
}
