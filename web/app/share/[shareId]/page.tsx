import { ShareClient } from './share-client'

export default async function SharePage({
  params,
}: {
  params: Promise<{ shareId: string }>
}) {
  const resolved = await params
  return <ShareClient shareId={resolved.shareId} />
}
