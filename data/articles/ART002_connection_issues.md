# Broadband Connection Issues — Troubleshooting Guide

**Article ID:** ART002  
**Category:** Technical / Connection  
**Last Updated:** 2024-01-15  

---

## Overview

This article covers diagnostic steps and resolutions for broadband connection issues including complete outages, slow speeds, intermittent drops, and Wi-Fi problems.

---

## Step 1 — Quick Triage Questions

Before running diagnostics, establish:
1. Is the issue affecting **all devices** or just one?
2. Is the issue **wired (Ethernet)** or **Wi-Fi** or both?
3. What do the **router lights** show? (Power, Broadband/WAN, Wi-Fi)
4. When did the issue start?
5. Has anything changed recently (new device, router moved, storm)?

---

## Scenario A — Complete Outage (No Internet on Any Device)

### Router Light Status Guide

| Broadband/WAN Light | Meaning |
|---|---|
| Solid Green | Line connected — issue is likely router or device |
| Flashing Green | Syncing — wait 2 minutes |
| Red or Off | Line fault — likely ISP-side issue |

### Resolution Steps

1. **Restart the router:** Unplug power for 60 seconds, plug back in, wait 3 minutes
2. **Check for area outage:** Look up account postcode in the outage tracker (internal tool)
3. **If area outage confirmed:** Inform customer of ETA, log ticket as outage-related, no engineer needed
4. **If no area outage:**
   - Check line signal levels remotely (use diagnostic tool)
   - If signal levels abnormal → schedule engineer visit
   - If signal levels normal → router fault suspected → arrange router replacement

### Common Causes
- Area network outage (check first)
- Loose or damaged cable at junction box
- Router hardware fault
- ISP equipment failure at exchange

---

## Scenario B — Slow Speeds

### Expected Speed Ranges by Plan

| Plan | Expected Download | Minimum Guaranteed |
|---|---|---|
| Fiber 100 | 100 Mbps | 50 Mbps |
| Fiber 500 | 500 Mbps | 250 Mbps |
| Fiber 1000 | 1000 Mbps | 500 Mbps |

**If speed is below minimum guaranteed, the customer is entitled to a remedy under our Speed Guarantee Policy.**

### Diagnosis Steps

1. Ask customer to run speed test at [speedtest.nexusnow.com] on a **wired** connection
2. If wired speed is above minimum → Wi-Fi issue (see Scenario C)
3. If wired speed is below minimum:
   - Check for local congestion (peak hours: 6 PM – 10 PM)
   - Run remote line diagnostics
   - If persistent (3+ days): schedule engineer visit
   - Log fault and apply bill credit if SLA is breached (1 day credit per 5 days below minimum)

---

## Scenario C — Wi-Fi Issues (Wired Works Fine)

**Resolution steps:**
1. Router placement: must be central, elevated, away from microwaves/cordless phones
2. Try changing Wi-Fi channel (auto-select in router settings)
3. If house is large: recommend Wi-Fi extender or mesh upgrade
4. Factory reset router as last resort (warn customer this clears custom settings)

---

## Scenario D — Intermittent Drops

Often caused by:
- Line noise (especially in older copper-fibre hybrid lines)
- Faulty microfilter or socket
- Interference from nearby equipment

**Steps:**
1. Check connection logs in the account portal for drop frequency/pattern
2. If drops are at specific times (e.g., evenings) → likely congestion or line noise
3. If random → run line noise diagnostic
4. Persistent drops → engineer visit required

---

## Escalation Criteria

Escalate to Level 2 Technical Support if:
- Issue persists after 2 engineer visits
- Signal levels are normal but outage continues
- Customer reports business-critical impact (working from home, medical device, etc.)
- Customer has been without service for more than 48 hours

---

## SLA and Compensation

| Outage Duration | Compensation |
|---|---|
| Under 24 hours | No automatic compensation |
| 24–48 hours | 1 day bill credit |
| 48–72 hours | 3 days bill credit |
| Over 72 hours | 5 days bill credit + review |

Credits are applied to the next bill automatically once the fault is marked resolved.
