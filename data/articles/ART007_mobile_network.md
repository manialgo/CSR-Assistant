# Mobile Network Issues — Signal, Calls, and Data

**Article ID:** ART007  
**Category:** Technical / Mobile  
**Last Updated:** 2024-01-15  

---

## Overview

This article covers troubleshooting for mobile network issues including poor signal, dropped calls, mobile data not working, and SMS delivery failures.

---

## Step 1 — Quick Triage

Establish these facts before diagnosing:

1. Is the issue affecting **calls**, **data**, or **both**?
2. Is it location-specific or everywhere?
3. Does the issue persist after restarting the phone?
4. When did it start?
5. Has anything changed (new phone, SIM replacement, software update, moved home)?

---

## Scenario A — No Signal / Very Weak Signal

### Check First
- Is there a known **network outage** in the area? (Check internal outage tracker)
- Is the customer in a basement, rural area, or building with thick walls?

### Steps
1. Restart the phone
2. Manually search for network: Settings → Mobile Network → Network Operators → Select manually → Choose NexusNow → Set back to automatic
3. Check if SIM is seated properly (remove and reinsert)
4. If issue is building-specific → indoor coverage limitation (note in ticket, no fix possible without signal booster — available for purchase)
5. If issue is widespread in the area → log as network complaint, flag to Network team

### Signal Booster
- Available for purchase: ₹1,499 for small premises, ₹2,999 for large premises
- Not covered under standard plan — paid add-on

---

## Scenario B — Mobile Data Not Working

### Steps
1. Confirm data is not exhausted — check data balance in MySelf app
2. Check APN settings:
   - **APN:** nexusnow.internet  
   - **Username:** (leave blank)  
   - **Password:** (leave blank)  
   - **MCC:** 404, **MNC:** 20
3. Toggle mobile data off and on
4. Restart phone
5. If still not working → re-provision data service (internal tool → Account → Re-provision Mobile Data → Submit)
6. Allow 15 minutes for re-provisioning to take effect

### Data Exhausted
- Customer on Mobile Basic (5 GB): data throttled to 64 Kbps after limit
- Customer on Mobile Plus (20 GB): data throttled to 128 Kbps after limit  
- Customer on Mobile Max (100 GB): Fair Use Policy applies above 100 GB — throttled to 512 Kbps
- Top-up available: ₹99 for 2 GB (valid 30 days), ₹199 for 5 GB (valid 30 days)

---

## Scenario C — Dropped Calls / Poor Call Quality

1. Check for area network issues first
2. VoLTE: ensure VoLTE is enabled on the phone (required for HD calling)
3. Wi-Fi Calling: if signal is weak indoors, enable Wi-Fi Calling as alternative
   - Settings → Mobile Network → Wi-Fi Calling → On
4. If calls drop in a specific location repeatedly → log as coverage complaint
5. Persistent call quality issues → escalate to Network team with location coordinates

---

## Scenario D — SMS Not Sending / Receiving

1. Restart phone
2. Check message centre number: must be **+919900012345** (Settings → Messages → Advanced → SMS Service Centre)
3. Check if recipient's number is blocked
4. If group SMS failing: disable MMS (some handsets require data for group messages)
5. Persistent failures → re-provision SMS service (same process as data re-provisioning)

---

## Escalation Criteria

Escalate to Network Team if:
- Issue affects multiple customers in same area (area fault)
- Customer in critical location with no coverage (hospital, school, emergency services)
- Issue persists after 3 troubleshooting sessions
- Customer reports emergency call failure (999/112 calls)

---

## Coverage Complaints

If a customer's signal issue is due to coverage rather than a fault:
- Log a formal coverage complaint in the system
- Network team reviews within 5 business days
- Customer receives written response with coverage assessment
- No guarantee of improvement — be honest with customer
