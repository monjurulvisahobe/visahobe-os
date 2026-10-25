# VisaHoBe OS — Cloud Deploy Guide (Render + Supabase)

## এই আপডেটে যা হলো
- `storage.py` যোগ হলো — ডুয়াল-মোড স্টোরেজ:
  - **LOCAL MODE** (আগের মতোই): `data/*.json` ফাইলে সব ডাটা
  - **CLOUD MODE**: Supabase Postgres-এ ডাটা — পারমানেন্ট, সব ডিভাইসে একসাথে
- প্রথমবার CLOUD MODE-এ চালু করলে আপনার এখনকার JSON ডাটা **অটো-মাইগ্রেট** হয়ে যাবে
- নতুন `/api/last_updated` + ফ্রন্টএন্ড পোলিং = কেউ কিছু বদলালে সবার স্ক্রিনে ৭ সেকেন্ডের মধ্যে আপডেট
- Supabase সার্ভিস-কী শুধু সার্ভারে থাকে — ব্রাউজার কখনো ডাটাবেজে সরাসরি ঢুকতে পারে না (RLS চালু)

## ধাপ ১: Supabase ফ্রি অ্যাকাউন্ট (~৩ মিনিট)
1. যান https://supabase.com → GitHub/Google দিয়ে সাইন আপ (ফ্রি)
2. **New Project** → নাম: `visahobe` → একটা স্ট্রং ডাটাবেজ পাসওয়ার্ড (সেভ রাখুন!) → Region: Singapore/Frankfurt → Create
3. প্রজেক্ট তৈরি হলে **SQL Editor** খুলুন → `supabase_schema.sql` ফাইলের পুরো কোড পেস্ট করে Run
4. **Settings → API** থেকে দুটো জিনিস কপি করুন:
   - **Project URL** (https://xxxx.supabase.co)
   - **service_role** key (গোপন! কাউকে দেখাবেন না)

## ধাপ ২: Render-এ অ্যাপ ডিপ্লয় (~৫ মিনিট)
1. যান https://render.com → সাইন আপ
2. **New → Web Service** → কোড দুইভাবে দেওয়া যায়:
   - সহজ: পুরো `visahobe-os` ফোল্ডারটা একটা GitHub রিপোতে পুশ করে সেটা কানেক্ট করুন
   - বা Render-এর "Deploy an existing image/manual" অপশন
3. সেটিংস:
   - Environment: **Docker** (render.yaml রেডি আছে)
   - Plan: **Free**
4. **Environment variables** যোগ করুন:
   - `SUPABASE_URL` = ধাপ ১-এর Project URL
   - `SUPABASE_SERVICE_KEY` = ধাপ ১-এর service_role key
   - বাকি GEMINI_KEY/GMAIL_* ইত্যাদি চাইলে পরে যোগ করবেন
5. Deploy → কয়েক মিনিটে লিংক পাবেন: `https://visahobe-os.onrender.com`

## ধাপ ৩: চেক
1. লিংক খুলুন → অ্যাপ চলবে
2. একটা ক্যান্ডিডেট যোগ করুন → Supabase ড্যাশবোর্ডে Table Editor → `app_data` টেবিলে ডাটা দেখতে পাবেন
3. অন্য ডিভাইসে খুললেও একই ডাটা — এখন থেকে ডাটা কখনো হারাবে না (Render রিস্টার্ট হলেও)

## খরচ
- Supabase ফ্রি টিয়ার: ৫০০MB ডাটাবেজ — ব্যক্তিগত এজেন্সির জন্য বছরের পর বছর যথেষ্ট
- Render ফ্রি টিয়ার: ৫০০ ঘণ্টা/মাস — অ্যাপ না-ব্যবহারে ১৫ মিনিট পর ঘুমায়, প্রথম ক্লিকে ৩০-৫০ সেকেন্ড দেরিতে জাগে। সমস্যা হলে Starter প্ল্যান ($7/মাস) নিলে সবসময় জেগে থাকবে
- মোট শুরুর খরচ: **৳০**

## নিরাপত্তা নোট
- `SUPABASE_SERVICE_KEY` কখনো GitHub-এ/চ্যাটে পাবলিক করবেন না — শুধু Render-এর Environment variables-এ
- অ্যাপে এখনো লগইন নেই — লিংক যার কাছে আছে সে এন্ট্রি দেখতে/এডিট করতে পারবে। পাবলিক শেয়ার না করে নিজের টিমের মধ্যে রাখুন। লগইন লাগলে পরে যোগ করা যাবে (বললেই বানিয়ে দেব)
