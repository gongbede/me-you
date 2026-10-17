import { createContext, useContext } from 'react'
import type { PlayableTrack } from '../components/MusicPlayer'

export type MusicPlayerContextValue = {
  playQueue: (tracks: PlayableTrack[], index: number) => Promise<void>
}

export const MusicPlayerContext = createContext<MusicPlayerContextValue | null>(null)

export function useMusicPlayer() {
  const value = useContext(MusicPlayerContext)
  if (!value) throw new Error('MusicPlayerProvider is missing')
  return value
}
