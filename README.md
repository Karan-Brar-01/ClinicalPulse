# ClinicalPulse 🩺⚡

> **Pre-Clinical Telehealth Triage Platform**  
> Contactless optical vitals (rPPG), cough acoustic intelligence, adaptive AI intake, and clinician SBAR decision support.

[![Live Web Application](https://img.shields.io/badge/Live_App-clinical--pulse--one.vercel.app-00DC82?style=for-the-badge&logo=vercel&logoColor=white)](https://clinical-pulse-one.vercel.app)
[![API Swagger Docs](https://img.shields.io/badge/API_Docs-FastAPI_Swagger-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://clinicalpulse-backen.onrender.com/docs)
[![Next.js 14](https://img.shields.io/badge/Frontend-Next.js_14-black?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Supabase](https://img.shields.io/badge/Database-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)

---

## 🌐 Live Deployments

* **Live Application:** [https://clinical-pulse-one.vercel.app](https://clinical-pulse-one.vercel.app)
* **Doctor Command Center:** [https://clinical-pulse-one.vercel.app/doctor](https://clinical-pulse-one.vercel.app/doctor)
* **Backend API & Swagger Docs:** [https://clinicalpulse-backen.onrender.com/docs](https://clinicalpulse-backen.onrender.com/docs)

---

## 🌟 Key Innovations & Features

### 1. 💬 Adaptive Clinical Intake
* Simulates an empathetic triage nurse gathering focused medical history.
* Evaluates chief complaint, duration, and red-flag symptoms (chest pain, shortness of breath, neurological deficits, syncope).
* Adapts follow-up questions dynamically turn-by-turn using high-speed LLM inference on Groq.

### 2. 📹 Contactless Optical Vitals (rPPG)
* **Remote Photoplethysmography (rPPG):** Measures micro-vascular blood volume pulsations directly from subtle facial color variations using the device webcam.
* Processes green-channel chromatic extraction, applies bandpass filtering, and utilizes Fast Fourier Transform (FFT) peak detection to extract **Heart Rate (BPM)** and **HRV (SDNN)** with real-time confidence metrics.

### 3. 🎙️ Acoustic Cough Classification
* Analyzes patient cough recordings through audio signal processing.
* Generates Mel-spectrograms and computes spectral features (centroid, bandwidth, zero-crossing rate) to classify dry vs. wet coughs, quantify acoustic severity, and detect adventitious sounds (wheezes/crackles).

### 4. 🧠 Multi-Modal Triage & Differential Synthesis
* Fuses conversational intake, biometric vitals, and acoustic telemetry into a standardized clinical **SBAR** report (*Situation, Background, Assessment, Recommendation*).
* Generates ranked **Differential Diagnoses** with ICD-10 codes, evidence rationale, and probability scores.
* Formulates physician decision-support recommendations and plain-language patient summaries.

### 5. 🏥 Doctor Command Center (`/doctor`)
* Queue of incoming triaged consultations sorted by urgency level (`ROUTINE`, `URGENT`, `EMERGENCY`).
* Detailed breakdown of telemetry, rPPG pulse waveforms, acoustic spectrograms, and symptom transcripts.
* Clinician sign-off workflow with notes editing and prescription approval.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│               Patient Web Portal (Next.js 14)          │
│   • Webcam Face Mesh (rPPG)  • Audio Cough Recorder    │
│   • Conversational Intake    • Patient Triage Report   │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTPS / REST
┌──────────────────────────▼─────────────────────────────┐
│                 FastAPI Telehealth Backend             │
│   • Computer Vision rPPG Signal Engine (NumPy/SciPy)   │
│   • Audio Acoustic Feature Extraction (Librosa/STFT)   │
│   • Clinical Triage & SBAR Synthesizer (Groq LLM)      │
│   • Hybrid Cloud / Local SQLite Fallback Persistence   │
└──────────────┬───────────────────────────┬─────────────┘
               │                           │
┌──────────────▼─────────────┐ ┌───────────▼─────────────┐
│    Supabase PostgreSQL     │ │  Doctor Command Center  │
│  (Cloud Consultation Store)│ │  (Clinician Review UI)  │
└────────────────────────────┘ └─────────────────────────┘
```

---

## 🛠️ Tech Stack

* **Frontend:** Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Lucide Icons, Recharts.
* **Backend:** FastAPI, Python 3.11, Uvicorn, Pydantic v2.
* **Biometrics & Signal Processing:** OpenCV, NumPy, SciPy, Librosa, SoundFile, Matplotlib.
* **AI & LLM Inference:** Groq Cloud (`openai/gpt-oss-120b`).
* **Database & Storage:** Supabase (PostgreSQL with RLS) + SQLite resilient fallback.
* **Deployment:** Vercel (Frontend) + Render Docker (Backend).

---

## 🚀 Local Development Setup

### Prerequisites
* Node.js 18+ & npm
* Python 3.9+ & venv

### 1. Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env file with your credentials:
# GROQ_API_KEY=your_groq_key
# SUPABASE_URL=your_supabase_url
# SUPABASE_KEY=your_supabase_key

uvicorn app.main:app --reload --port 8000
```
Backend Swagger docs will be live at `http://127.0.0.1:8000/docs`.

### 2. Frontend Setup
```bash
cd frontend
npm install

# Create .env.local
# NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
# BACKEND_URL=http://127.0.0.1:8000

npm run dev
```
Open [http://localhost:3000](http://localhost:3000) for the patient intake or [http://localhost:3000/doctor](http://localhost:3000/doctor) for the doctor portal.

---

## 📄 License
MIT License. Built for clinical triage prototyping and telehealth research.
