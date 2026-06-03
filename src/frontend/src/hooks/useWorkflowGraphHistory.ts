import { useCallback, useRef, type Dispatch, type SetStateAction } from 'react'
import type { Edge, Node, NodeChange, EdgeChange } from '@xyflow/react'

type Snapshot = { nodes: Node[]; edges: Edge[] }

const MAX_HISTORY = 50

function cloneGraph(nodes: Node[], edges: Edge[]): Snapshot {
  return {
    nodes: structuredClone(nodes),
    edges: structuredClone(edges),
  }
}

export function useWorkflowGraphHistory(
  nodes: Node[],
  edges: Edge[],
  setNodes: Dispatch<SetStateAction<Node[]>>,
  setEdges: Dispatch<SetStateAction<Edge[]>>,
) {
  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)
  nodesRef.current = nodes
  edgesRef.current = edges

  const pastRef = useRef<Snapshot[]>([])
  const futureRef = useRef<Snapshot[]>([])
  const dragSnapshotTakenRef = useRef(false)

  const clearHistory = useCallback(() => {
    pastRef.current = []
    futureRef.current = []
    dragSnapshotTakenRef.current = false
  }, [])

  const pushHistory = useCallback(() => {
    pastRef.current.push(cloneGraph(nodesRef.current, edgesRef.current))
    if (pastRef.current.length > MAX_HISTORY) pastRef.current.shift()
    futureRef.current = []
  }, [])

  const undo = useCallback(() => {
    if (pastRef.current.length === 0) return false
    futureRef.current.push(cloneGraph(nodesRef.current, edgesRef.current))
    const prev = pastRef.current.pop()!
    setNodes(prev.nodes)
    setEdges(prev.edges)
    return true
  }, [setEdges, setNodes])

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return false
    pastRef.current.push(cloneGraph(nodesRef.current, edgesRef.current))
    const next = futureRef.current.pop()!
    setNodes(next.nodes)
    setEdges(next.edges)
    return true
  }, [setEdges, setNodes])

  const onNodeDragStart = useCallback(() => {
    if (dragSnapshotTakenRef.current) return
    dragSnapshotTakenRef.current = true
    pushHistory()
  }, [pushHistory])

  const onNodeDragStop = useCallback(() => {
    dragSnapshotTakenRef.current = false
  }, [])

  const handleNodesChange = useCallback(
    (changes: NodeChange[], apply: (changes: NodeChange[]) => void) => {
      if (changes.some((c) => c.type === 'remove')) pushHistory()
      apply(changes)
    },
    [pushHistory],
  )

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[], apply: (changes: EdgeChange[]) => void) => {
      if (changes.some((c) => c.type === 'remove')) pushHistory()
      apply(changes)
    },
    [pushHistory],
  )

  return {
    pushHistory,
    undo,
    redo,
    clearHistory,
    onNodeDragStart,
    onNodeDragStop,
    handleNodesChange,
    handleEdgesChange,
    canUndo: () => pastRef.current.length > 0,
    canRedo: () => futureRef.current.length > 0,
  }
}
