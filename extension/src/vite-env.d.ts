/// <reference types="svelte" />
/// <reference types="vite/client" />

declare module '*.svelte?inline' {
  const content: string
  export default content
}
