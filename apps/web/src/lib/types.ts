export type User = {
  updated_at: string;
  id: string;
  email: string;
  display_name: string;
  role: string;
  status: string;
  department_id: string | null;
};
export type CustomField = {
  key: string;
  name_ru: string;
  name_en: string;
  kind: string;
  required: boolean;
  enabled: boolean;
  default: unknown;
  options: string[];
  order: number;
  minimum: number | null;
  maximum: number | null;
  max_length: number;
};
export type Catalog = {
  updated_at?: string;
  metadata_schema?: { fields?: CustomField[] };
  id: string;
  code: string;
  name_ru: string;
  name_en: string;
};
export type Folder = {
  updated_at: string;
  id: string;
  name: string;
  parent_id: string | null;
  owner_id: string;
};
export type Document = {
  capabilities: Record<string, boolean>;
  description: string;
  category: string;
  tags: string[];
  responsible_id: string | null;
  confidentiality: string;
  effective_date: string | null;
  expiration_date: string | null;
  folder_id: string | null;
  deleted_at: string | null;
  revision: number;
  id: string;
  number: string;
  title: string;
  type_id: string;
  owner_id: string;
  department_id: string | null;
  status: string;
  business_metadata: Record<string, unknown>;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
};
export type Version = {
  id: string;
  version_number: number;
  original_filename: string;
  mime_type: string;
  size: number;
  sha256: string;
  change_note: string | null;
  created_at: string;
};
export type Comment = {
  id: string;
  author_id: string;
  body: string;
  created_at: string;
};
export type Activity = {
  id: string;
  action: string;
  actor_id: string | null;
  created_at: string;
  request_id?: string;
  target_id?: string;
};
export type DocumentList = { items: Document[]; total: number; page: number };
export type Dashboard = {
  my_documents: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  recent: Document[];
};

export type WorkflowStage = {
  name_ru: string;
  name_en: string;
  selector: string;
  targets: string[];
  due_hours: number;
  require_comment: boolean;
  conditions: { field: string; op: string; value: unknown }[];
};
export type WorkflowTemplate = {
  id: string;
  code: string;
  version: number;
  name_ru: string;
  name_en: string;
  stages: WorkflowStage[];
};
export type WorkflowInstance = {
  id: string;
  document_id: string;
  document_version_id: string;
  status: string;
  stage: number;
  template: WorkflowTemplate;
  created_at: string;
  completed_at: string | null;
  approvals: {
    id: string;
    user_id: string;
    display_name: string;
    stage: number;
    status: string;
    due_at: string | null;
    acted_at: string | null;
    name_ru: string;
    name_en: string;
    mine: boolean;
  }[];
  events: {
    id: string;
    actor_id: string;
    display_name: string;
    action: string;
    comment: string;
    previous_state: string;
    new_state: string;
    created_at: string;
  }[];
};
