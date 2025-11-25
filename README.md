# The Philosophy Forum Archive Generator

A high-performance static site generator that transforms Plush Forums data exports into a permanent, searchable read-only archive.

## 🚀 Overview

This custom-built system converts the historical data from **The Philosophy Forum (TPF)** (2015-2026) into a fully functional static website, preserving over 15,000 user discussions and 150,000+ comments after the forum's migration to Discourse.

## 💡 Why This Exists

When TPF moved from Plush Forums to Discourse in 2026, this project ensured that:
- 10+ years of philosophical discussions remain accessible
- User contributions are permanently preserved
- The archive remains fully searchable and navigable
- All content is available without database dependencies

## 🛠 Technical Highlights

**Performance Optimizations**
- Lazy-loaded user data chunks for instant search (reduced load times from 20+ seconds to <100ms)
- Pre-rendered search indexes for username lookups
- Optimized BBCode-to-HTML conversion with custom parser
- Chunked data loading serving 15,000+ users efficiently

**Key Features**
- Full-text search across all discussions and comments
- User post history with downloadable archives
- Category-based filtering and navigation
- Responsive design for all devices
- SEO-optimized static HTML output

## 🏗 Architecture
Raw Plush Forums JSON Export  
↓  
Custom Python Parser & Converter  
↓  
Optimized Static HTML + Search Indexes  
↓  
Deployable Archive Website  

## 📊 Scale & Performance
- 15,000+ users with post histories
- 150,000+ comments across all discussions
- Search performance: <100ms for any user lookup
- Build time: ~15 minutes for full site generation
- Output: 100% static HTML/CSS/JS

*This archive preserves the philosophical discussions from [The Philosophy Forum](https://thephilosophyforum.com) between 2015-2026 during its Plush Forums era.*