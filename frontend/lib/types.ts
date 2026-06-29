export interface Profile {
  id: string;
  email: string;
  display_name: string | null;
  locale: string;
  status: string;
  roles: string[];
  email_verified: boolean;
  created_at: string;
}

export interface Style {
  id: string;
  slug: string;
  name: string;
  category: string;
  description: string | null;
  cost_multiplier: number;
  plan_gate: string | null;
}

export interface Job {
  id: string;
  status: string;
  progress: number;
  cost_credits: number;
  prompt: string;
  stages: string[];
  error_message: string | null;
  created_at: string;
  result_image_ids: string[];
}

export interface GalleryItem {
  id: string;
  kind: string;
  mime: string;
  width: number | null;
  height: number | null;
  visibility: string;
  is_favorite: boolean;
  share_token: string | null;
  url: string;
  created_at: string;
}

export interface Plan {
  id: string;
  slug: string;
  name: string;
  kind: string;
  monthly_credits: number;
  credits: number;
  price_cents: number;
  currency: string;
}

export interface Balance {
  balance: number;
  held: number;
  available: number;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}
