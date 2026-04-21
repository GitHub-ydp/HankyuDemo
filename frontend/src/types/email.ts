export interface EmailItem {
  id: string;
  subject: string;
  from: string;
  from_name: string;
  to: string;
  date: string;
  score: number;
  content: string;
  category: string;
  tags: string;
  has_attachment: string;
  folder: string;
}

export interface EmailSearchResponse {
  query: string;
  count: number;
  results: EmailItem[];
}

export interface EmailAnalyzeResponse {
  query: string;
  count: number;
  emails: EmailItem[];
  analysis: string;
}

export interface EmailIndexResponse {
  status: string;
  count: number;
  emails: EmailItem[];
}
