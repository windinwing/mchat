/** Map backend knowledge API (snake_case) to UI types */

export type ChunkStrategy = 'fixed' | 'paragraph' | 'markdown' | 'semantic'
export type RetrievalMode = 'vector' | 'keyword' | 'hybrid'
export type RerankProvider = 'none' | 'lexical' | 'cohere' | 'bge' | 'cross-encoder'

export interface KnowledgeBaseRagSettings {
  chunkStrategy: ChunkStrategy
  chunkSize: number
  chunkOverlap: number
  chunkMinSize: number
  chunkSemanticThreshold: number
  chunkParentEnabled: boolean
  embeddingProvider?: string
  embeddingModel?: string
  embeddingApiBase?: string
  embeddingDimension: number
  retrievalMode: RetrievalMode
  retrievalTopK: number
  retrievalCandidateK: number
  rerankEnabled: boolean
  rerankTopN: number
  rerankProvider: RerankProvider
  rerankModel?: string
  retrievalBm25Enabled: boolean
  retrievalBm25K1: number
  retrievalBm25B: number
  retrievalQueryRewriteEnabled: boolean
  retrievalQueryRewriteCount: number
}

export interface KnowledgeBase extends KnowledgeBaseRagSettings {
  id: string
  groupId?: string | null
  name: string
  description?: string
  documentCount: number
  indexedEmbeddingKey?: string
  needsReindex: boolean
  reindexStatus: 'idle' | 'running' | 'completed' | 'failed'
  createdAt: string
  updatedAt: string
}

export interface KnowledgeDocument {
  id: string
  knowledgeBaseId: string
  filename: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'indexed'
  fileSize: number
  createdAt: string
}

const defaultRag: KnowledgeBaseRagSettings = {
  chunkStrategy: 'fixed',
  chunkSize: 500,
  chunkOverlap: 50,
  chunkMinSize: 80,
  chunkSemanticThreshold: 0.7,
  chunkParentEnabled: true,
  embeddingDimension: 1536,
  retrievalMode: 'hybrid',
  retrievalTopK: 5,
  retrievalCandidateK: 20,
  rerankEnabled: true,
  rerankTopN: 5,
  rerankProvider: 'lexical',
  retrievalBm25Enabled: true,
  retrievalBm25K1: 1.5,
  retrievalBm25B: 0.75,
  retrievalQueryRewriteEnabled: false,
  retrievalQueryRewriteCount: 3,
}

function mapRagFields(raw: Record<string, unknown>): KnowledgeBaseRagSettings {
  return {
    chunkStrategy: (raw.chunk_strategy as ChunkStrategy) ?? defaultRag.chunkStrategy,
    chunkSize: Number(raw.chunk_size ?? defaultRag.chunkSize),
    chunkOverlap: Number(raw.chunk_overlap ?? defaultRag.chunkOverlap),
    chunkMinSize: Number(raw.chunk_min_size ?? defaultRag.chunkMinSize),
    chunkSemanticThreshold: Number(raw.chunk_semantic_threshold ?? defaultRag.chunkSemanticThreshold),
    chunkParentEnabled: raw.chunk_parent_enabled !== false && raw.chunk_parent_enabled !== 0,
    embeddingProvider:
      raw.embedding_provider != null ? String(raw.embedding_provider) : undefined,
    embeddingModel:
      raw.embedding_model != null ? String(raw.embedding_model) : undefined,
    embeddingApiBase:
      raw.embedding_api_base != null ? String(raw.embedding_api_base) : undefined,
    embeddingDimension: Number(raw.embedding_dimension ?? defaultRag.embeddingDimension),
    retrievalMode: (raw.retrieval_mode as RetrievalMode) ?? defaultRag.retrievalMode,
    retrievalTopK: Number(raw.retrieval_top_k ?? defaultRag.retrievalTopK),
    retrievalCandidateK: Number(
      raw.retrieval_candidate_k ?? defaultRag.retrievalCandidateK,
    ),
    rerankEnabled: raw.rerank_enabled !== false && raw.rerank_enabled !== 0,
    rerankTopN: Number(raw.rerank_top_n ?? defaultRag.rerankTopN),
    rerankProvider: (raw.rerank_provider as RerankProvider) ?? defaultRag.rerankProvider,
    rerankModel: raw.rerank_model != null ? String(raw.rerank_model) : undefined,
    retrievalBm25Enabled: raw.retrieval_bm25_enabled !== false && raw.retrieval_bm25_enabled !== 0,
    retrievalBm25K1: Number(raw.retrieval_bm25_k1 ?? defaultRag.retrievalBm25K1),
    retrievalBm25B: Number(raw.retrieval_bm25_b ?? defaultRag.retrievalBm25B),
    retrievalQueryRewriteEnabled: raw.retrieval_query_rewrite_enabled === true || raw.retrieval_query_rewrite_enabled === 1,
    retrievalQueryRewriteCount: Number(raw.retrieval_query_rewrite_count ?? defaultRag.retrievalQueryRewriteCount),
  }
}

export function ragSettingsToPayload(
  settings: KnowledgeBaseRagSettings,
): Record<string, unknown> {
  return {
    chunk_strategy: settings.chunkStrategy,
    chunk_size: settings.chunkSize,
    chunk_overlap: settings.chunkOverlap,
    chunk_min_size: settings.chunkMinSize,
    chunk_semantic_threshold: settings.chunkSemanticThreshold,
    chunk_parent_enabled: settings.chunkParentEnabled,
    embedding_provider: settings.embeddingProvider || null,
    embedding_model: settings.embeddingModel || null,
    embedding_api_base: settings.embeddingApiBase || null,
    embedding_dimension: settings.embeddingDimension,
    retrieval_mode: settings.retrievalMode,
    retrieval_top_k: settings.retrievalTopK,
    retrieval_candidate_k: settings.retrievalCandidateK,
    rerank_enabled: settings.rerankEnabled,
    rerank_top_n: settings.rerankTopN,
    rerank_provider: settings.rerankProvider,
    rerank_model: settings.rerankModel || null,
    retrieval_bm25_enabled: settings.retrievalBm25Enabled,
    retrieval_bm25_k1: settings.retrievalBm25K1,
    retrieval_bm25_b: settings.retrievalBm25B,
    retrieval_query_rewrite_enabled: settings.retrievalQueryRewriteEnabled,
    retrieval_query_rewrite_count: settings.retrievalQueryRewriteCount,
  }
}

export function mapKnowledgeBase(raw: Record<string, unknown>): KnowledgeBase {
  return {
    id: String(raw.id),
    groupId: raw.group_id != null ? String(raw.group_id) : null,
    name: String(raw.name),
    description: raw.description != null ? String(raw.description) : undefined,
    documentCount: Number(raw.document_count ?? raw.documentCount ?? 0),
    indexedEmbeddingKey:
      raw.indexed_embedding_key != null
        ? String(raw.indexed_embedding_key)
        : undefined,
    needsReindex: Boolean(raw.needs_reindex),
    reindexStatus: (raw.reindex_status as KnowledgeBase['reindexStatus']) ?? 'idle',
    createdAt: String(raw.created_at ?? raw.createdAt ?? ''),
    updatedAt: String(raw.updated_at ?? raw.updatedAt ?? ''),
    ...mapRagFields(raw),
  }
}

export interface UploadedEmbeddingModel {
  id: string
  name: string
  status: 'processing' | 'ready' | 'failed'
  dimension: number
  fileSize: number
  errorMessage?: string
  createdAt: string
}

export function mapUploadedEmbeddingModel(
  raw: Record<string, unknown>,
): UploadedEmbeddingModel {
  return {
    id: String(raw.id),
    name: String(raw.name),
    status: String(raw.status ?? 'processing') as UploadedEmbeddingModel['status'],
    dimension: Number(raw.dimension ?? 0),
    fileSize: Number(raw.file_size ?? 0),
    errorMessage:
      raw.error_message != null ? String(raw.error_message) : undefined,
    createdAt: String(raw.created_at ?? ''),
  }
}

export interface ReindexResult {
  knowledgeBaseId: string
  total: number
  succeeded: number
  failed: number
  rechunk: boolean
  milvusEnabled: boolean
}

export function mapReindexResult(raw: Record<string, unknown>): ReindexResult {
  return {
    knowledgeBaseId: String(raw.knowledge_base_id ?? ''),
    total: Number(raw.total ?? 0),
    succeeded: Number(raw.succeeded ?? 0),
    failed: Number(raw.failed ?? 0),
    rechunk: Boolean(raw.rechunk),
    milvusEnabled: Boolean(raw.milvus_enabled),
  }
}

export function mapDocument(raw: Record<string, unknown>): KnowledgeDocument {
  const status = String(raw.status ?? 'pending')
  return {
    id: String(raw.id),
    knowledgeBaseId: String(raw.knowledge_base_id ?? raw.knowledgeBaseId ?? ''),
    filename: String(raw.title ?? raw.filename ?? '未命名'),
    status: status === 'indexed' ? 'completed' : (status as KnowledgeDocument['status']),
    fileSize: Number(raw.file_size ?? raw.fileSize ?? 0),
    createdAt: String(raw.created_at ?? raw.createdAt ?? ''),
  }
}

export function uiStatusLabel(status: string): string {
  switch (status) {
    case 'completed':
    case 'indexed':
      return '已完成'
    case 'processing':
      return '处理中'
    case 'failed':
      return '失败'
    default:
      return '待处理'
  }
}

export { defaultRag }
