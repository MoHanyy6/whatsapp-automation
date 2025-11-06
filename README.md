# WhatsApp Automation with Flask & Twilio

A simple **Flask application** that automatically sends WhatsApp messages for shipment updates using **Twilio**. The app uses **Pyngrok** to create a public URL, so you can test webhooks from Oracle Transportation Management (OTM) or any system without deploying to a server.  

---

## Features

- Automatically sends WhatsApp messages for shipment updates.  
- Only sends **new updates**, preventing duplicate messages.  
- Temporary **public URL** generated automatically via Pyngrok (no manual Ngrok setup required).  
- View all messages sent via `/show-log`.  
- Easy setup using a `.env` file for Twilio credentials and port configuration.  

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/YourUsername/whatsapp-automation.git
cd whatsapp-automation
