export type User = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  status: string;
  department_id: string | null;
};
export type Catalog = {
  id: string;
  code: string;
  name_ru: string;
  name_en: string;
};
export type Document = {
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
