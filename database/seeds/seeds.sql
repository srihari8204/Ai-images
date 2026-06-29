-- =============================================================================
-- Seed data (plans, styles, feature flags).
-- Canonical seeding is `python -m app.db.seed` (idempotent). This SQL mirror is
-- provided for environments that prefer applying seeds directly via psql.
-- =============================================================================

-- ---- Plans & credit packs -------------------------------------------------
INSERT INTO plans (id, slug, name, kind, monthly_credits, credits, price_cents, currency, features, is_active, created_at, updated_at) VALUES
 (gen_random_uuid(), 'free',     'Free',        'subscription', 20,   0, 0,    'USD', '{"priority": false}', true, now(), now()),
 (gen_random_uuid(), 'pro',      'Pro',         'subscription', 500,  0, 1500, 'USD', '{"priority": true, "premium_styles": true}', true, now(), now()),
 (gen_random_uuid(), 'studio',   'Studio',      'subscription', 2000, 0, 4900, 'USD', '{"priority": true, "premium_styles": true}', true, now(), now()),
 (gen_random_uuid(), 'pack_100', '100 Credits', 'credit_pack',  0,  100, 900,  'USD', '{}', true, now(), now()),
 (gen_random_uuid(), 'pack_500', '500 Credits', 'credit_pack',  0,  500, 3900, 'USD', '{}', true, now(), now())
ON CONFLICT (slug) DO NOTHING;

-- ---- Styles ---------------------------------------------------------------
INSERT INTO styles (id, slug, name, category, template, negative_prompt, model_ref, lora_refs, default_params, cost_multiplier, plan_gate, is_active, created_at, updated_at) VALUES
 (gen_random_uuid(), 'photoreal',    'Photorealistic', 'general',      '{prompt}, ultra realistic, 8k, sharp focus, natural lighting', 'cartoon, painting, blurry, lowres, deformed', 'flux.1', '[]', '{"steps": 28, "guidance": 3.5}', 1.0, NULL,  true, now(), now()),
 (gen_random_uuid(), 'cinematic',    'Cinematic',      'general',      'cinematic still of {prompt}, dramatic lighting, film grain, shallow depth of field', 'flat lighting, snapshot, lowres', 'flux.1', '[]', '{"steps": 30, "guidance": 4.0}', 1.0, NULL,  true, now(), now()),
 (gen_random_uuid(), 'anime',        'Anime',          'illustration', 'anime illustration of {prompt}, vibrant colors, clean line art', 'photorealistic, 3d render, blurry', 'flux.1', '[]', '{"steps": 26, "guidance": 5.0}', 1.0, NULL,  true, now(), now()),
 (gen_random_uuid(), 'portrait_pro', 'Portrait Pro',   'portrait',     'professional studio portrait of {prompt}, softbox lighting, bokeh', 'harsh shadows, overexposed, distorted face', 'flux.1', '[]', '{"steps": 32, "guidance": 3.5}', 1.5, 'pro', true, now(), now()),
 (gen_random_uuid(), 'fantasy_art',  'Fantasy Art',    'illustration', 'epic fantasy concept art of {prompt}, intricate detail, painterly', 'photo, modern, lowres', 'flux.1', '[]', '{"steps": 34, "guidance": 5.5}', 1.5, 'pro', true, now(), now())
ON CONFLICT (slug) DO NOTHING;

-- ---- Feature flags --------------------------------------------------------
INSERT INTO feature_flags (key, value, description, created_at, updated_at) VALUES
 ('model.flux.enabled',      '{"enabled": true}', 'Enable FLUX.1 base model', now(), now()),
 ('model.instantid.enabled', '{"enabled": true}', 'Enable InstantID face consistency', now(), now()),
 ('queue.max_concurrency',   '{"value": 4}',      'Worker max concurrent jobs', now(), now()),
 ('registration.open',       '{"enabled": true}', 'Allow new sign-ups', now(), now())
ON CONFLICT (key) DO NOTHING;
