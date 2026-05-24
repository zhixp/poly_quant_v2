# 🧠 Gemini Model Guide - PolyQuant

## ✅ **Current Configuration (WORKING)**

```python
# app/config.py
GEMINI_MODEL = "models/gemini-2.0-flash"  # Stable, fast, reliable
```

---

## 📋 **Available Gemini Models (Dec 2025)**

### **Flash Models (Recommended for Speed):**

| Model Name | Speed | Quality | Status | Use Case |
|------------|-------|---------|--------|----------|
| `models/gemini-2.5-flash` | ⚡⚡⚡ | ⭐⭐⭐⭐ | Newest | Bleeding edge |
| `models/gemini-2.0-flash` | ⚡⚡⚡ | ⭐⭐⭐⭐ | ✅ **STABLE** | **Production (Current)** |
| `models/gemini-2.0-flash-001` | ⚡⚡⚡ | ⭐⭐⭐⭐ | Pinned | Version lock |
| ~~`gemini-1.5-flash`~~ | ❌ | ❌ | DEPRECATED | Don't use |

### **Pro Models (Higher Quality, Slower):**

| Model Name | Speed | Quality | Status | Use Case |
|------------|-------|---------|--------|----------|
| `models/gemini-2.0-pro` | ⚡⚡ | ⭐⭐⭐⭐⭐ | Stable | Complex analysis |
| `models/gemini-1.5-pro` | ⚡⚡ | ⭐⭐⭐⭐⭐ | Legacy | Still works |

---

## 🔧 **How to Change Models**

### **Option 1: Edit `app/config.py`**

```python
# Fastest (Current)
GEMINI_MODEL = "models/gemini-2.0-flash"

# Newest features
GEMINI_MODEL = "models/gemini-2.5-flash"

# Higher quality (slower)
GEMINI_MODEL = "models/gemini-2.0-pro"
```

### **Option 2: Environment Variable (Future)**

Add to `.env`:
```env
GEMINI_MODEL=models/gemini-2.0-flash
```

Then update `app/config.py`:
```python
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash")
```

---

## 🐛 **Common Errors & Solutions**

### **Error: `404 models/gemini-1.5-flash is not found`**

**Cause:** Old model name from 2024  
**Solution:** Update to `models/gemini-2.0-flash` ✅

### **Error: `API version v1beta not supported`**

**Cause:** Old `google-generativeai` library (< 0.8.0)  
**Solution:** 
```bash
pip install google-generativeai --upgrade
```

### **Error: `Model name must include 'models/' prefix`**

**Cause:** Using short name like `gemini-2.0-flash`  
**Solution:** Add prefix: `models/gemini-2.0-flash` ✅

---

## 📊 **Model Comparison**

### **Gemini 2.0 Flash (Current)**
- **Speed:** ~2-3 seconds per response
- **Cost:** $0.075 per 1M input tokens
- **RPM:** 15 requests/minute (free tier)
- **Best for:** Real-time trading signals, high-frequency queries

### **Gemini 2.5 Flash (Newest)**
- **Speed:** ~2-3 seconds per response
- **Cost:** Similar to 2.0
- **RPM:** 15 requests/minute (free tier)
- **Best for:** Latest features, experimental

### **Gemini 2.0 Pro**
- **Speed:** ~5-8 seconds per response
- **Cost:** $1.25 per 1M input tokens (16x more expensive!)
- **RPM:** 2 requests/minute (free tier)
- **Best for:** Deep research, complex multi-step reasoning

---

## 🎯 **Recommendations**

### **For PolyQuant (Current Setup):**
```python
✅ RECOMMENDED: "models/gemini-2.0-flash"
```

**Why?**
- ✅ Stable and battle-tested
- ✅ Fast enough for real-time alerts (<3s)
- ✅ Accurate for market analysis
- ✅ High RPM (15/min = 900/hour)
- ✅ Cost-effective

### **When to Upgrade to 2.5 Flash:**
- ⚠️ If 2.0 has stability issues
- ⚠️ If you need latest features
- ⚠️ After 2.5 is marked "stable"

### **When to Use Pro:**
- ⚠️ For deep research reports (not real-time)
- ⚠️ For complex legal contract analysis
- ⚠️ When accuracy > speed

---

## 🧪 **How to Test a Model**

Run this in Discord:
```
/ask question:Will Bitcoin hit 100k in 2025?
```

**Expected response time:**
- Flash: 2-3 seconds ✅
- Pro: 5-8 seconds

**Check logs for:**
```
✅ No "404 model not found" errors
✅ Response time < 5 seconds
✅ Agent council completes successfully
```

---

## 📚 **Version History**

| Date | Model | Reason |
|------|-------|--------|
| Dec 1, 2025 | `models/gemini-2.0-flash` | ✅ Current (Stable) |
| Nov 2024 | `gemini-1.5-flash-latest` | ❌ Deprecated `-latest` suffix |
| Pre-Nov 2024 | `gemini-1.5-flash` | ❌ Model removed by Google |

---

## 🔗 **Official Documentation**

- [Gemini API Models](https://ai.google.dev/gemini-api/docs/models/gemini)
- [Pricing](https://ai.google.dev/pricing)
- [Rate Limits](https://ai.google.dev/gemini-api/docs/quota)

---

**Last Updated:** Dec 1, 2025  
**Current Model:** `models/gemini-2.0-flash` ✅

