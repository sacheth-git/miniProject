"""Verify candidate ATS board tokens and write data/seeds/companies.yaml.

Each candidate token is tried on Greenhouse, Lever and Ashby public job-board APIs
(official, unauthenticated endpoints meant for embedding job boards). Only tokens
that respond with at least one open job are kept. India-located jobs are counted
so India-heavy companies are preferred when trimming to the target size.

Usage (from backend/): .\\.venv\\Scripts\\python.exe scripts\\verify_companies.py [--target 150]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml

OUT = Path(__file__).resolve().parents[1] / "data" / "seeds" / "companies.yaml"
UA = {"User-Agent": "HireX/0.1 (academic project; board verification)"}

# Candidate tokens (guesses from public careers pages). Verification decides.
CANDIDATES = """
razorpay phonepe groww meesho cred zeta sharechat mohalla dream11 dreamsports swiggy zomato zepto
blinkit inmobi glance juspay setu khatabook unacademy upgrad vedantu practo curefit urbancompany
nykaa paytm olacabs rapido dunzo licious porter delhivery cars24 spinny acko godigit policybazaar
oyo makemytrip bookmyshow gupshup exotel yellowai haptik observeai sigmoid tigeranalytics fractal
quantiphi tredence latentview gramener browserstack postman druva freshworks chargebee whatfix
darwinbox clevertap moengage sprinklr innovaccer thoughtspot mindtickle hasura slice jupiter fampay
cleartax clear rubrik nutanix uniphore lenskart purplle mamaearth boat cultfit healthifyme
pharmeasy 1mg tata1mg zetwerk infra.market ofbusiness moglix udaan jar fi niyo smallcase
zerodha upstox angelone indmoney navi kreditbee lendingkart mswipe pinelabs billdesk cashfree
payu easebuzz instamojo m2p perfios signzy idfy hyperverge bureau sarvam krutrim ola olaelectric
atherenergy ather ultraviolette simpleenergy yulu bounce chalo shuttl blackbuck rivigo shiprocket
pickrr ecomexpress xpressbees shadowfax loadshare locus fareye stockgro groyyo
airbnb stripe databricks cloudflare gitlab figma robinhood coinbase dropbox pinterest reddit
discord twilio okta mongodb elastic hashicorp datadog confluent cockroachlabs anthropic scaleai
brex lyft instacart doordash airtable notion asana intercom vercel netlify supabase linear openai
cohere ramp rippling deel remotecom gusto plaid chime affirm sofi toast canva grammarly duolingo
samsara verkada benchling flexport faire gong mixpanel amplitude segment launchdarkly pagerduty
newrelic sentry grafanalabs temporal fivetran dbtlabs starburst clickhouse singlestore yugabyte
pinecone weaviate huggingface replicate modal perplexityai mistral runwayml jasper writer
glean harvey hebbia sierra decagon cresta observe alation collibra sisense thoughtworks
zscaler crowdstrike sentinelone snyk wiz lacework tenable rapid7 arcticwolf abnormalsecurity
1password bitwarden tailscale docker circleci jfrog harness atlan hevodata hevo
appsmith tooljet chatwoot rocketchat frappe erpnext zoho zohocorp freshdesk kissflow
icertis mfine sharechat-tech quizizz classplus testbook adda247 physicswallah pw scaler
interviewbit simplilearn greatlearning byjus whitehatjr toppr eruditus emeritus coursera
udemy edx skillshare masterclass khanacademy
nvidia amd intel qualcomm arm synopsys cadence marvell micron texasinstruments
salesforce atlassian shopify hubspot zendesk servicenow workday adobe autodesk intuit
uber grab gojek agoda booking expedia tripadvisor trivago
spotify netflix roblox unity epicgames riotgames
wayfair etsy ebay poshmark mercari chewy
""".split()

# Second round (incremental): only probed when not already decided.
EXTRA_CANDIDATES = """
hackerrank hackerearth unstop turing toptal cleartrip goibibo ixigo redbus yatra dailyhunt verse josh
pocketfm kukufm stage eloelo winzo mpl games24x7 nazara zupee junglee headout rebelfoods magicpin
nobroker housing squareyards livspace homelane pepperfry urbanladder wakefit bewakoof myntra ajio
bigbasket citymall dealshare apna workindia vahan betterplace springworks keka greythr leena wingify
lambdatest testsigma kissflow zluri sprinto scrut rocketlane everstage fyle spendflo zeni togai plivo
ozonetel knowlarity verloop engati netcore webengage insider capillary zinier ninjacart dehaat agrostar
arya bijak waycool mintoak decentro open eko moneyview fibe stashfin kissht simpl uni onecard freo
scapia kiwi tide airwallex nium thunes rapyd checkout adyen klarna wise monzo revolut n26 nubank mercury
pleo qonto personio hibob lattice cultureamp leapsome workato tray zapier n8n retool airbyte prefect
dagster astronomer hightouch census rudderstack posthog heap fullstory contentsquare hotjar pendo
appcues userpilot gainsight totango vitally clari outreach salesloft apollo zoominfo 6sense demandbase
highspot seismic showpad docebo 360learning thinkific teachable kajabi miro loom calendly typeform
webflow framer zeplin invision lucid smartsheet monday clickup wrike coda mural pitch descript
""".split()

ATS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    "lever": "https://api.lever.co/v0/postings/{t}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{t}",
}
INDIA = re.compile(
    r"india|bengaluru|bangalore|mumbai|pune|hyderabad|chennai|gurugram|gurgaon|noida|delhi|kolkata|ahmedabad|jaipur|kochi|coimbatore|mysuru|indore|chandigarh",
    re.I,
)


def _locations(ats: str, data: Any) -> list[str]:
    if ats == "greenhouse":
        return [(j.get("location") or {}).get("name", "") for j in data.get("jobs", [])]
    if ats == "lever":
        return [(j.get("categories") or {}).get("location", "") or "" for j in data]
    return [j.get("location", "") or "" for j in data.get("jobs", [])]


def probe(client: httpx.Client, token: str) -> dict[str, Any] | None:
    for ats, tpl in ATS.items():
        try:
            r = client.get(tpl.format(t=token), timeout=20)
        except httpx.HTTPError as exc:
            print(f"  {token}@{ats}: network error {exc!r}", file=sys.stderr)
            continue
        if r.status_code != 200:
            continue
        try:
            data = r.json()
        except ValueError:
            continue
        locs = _locations(ats, data)
        if locs:
            india = sum(1 for loc in locs if INDIA.search(loc))
            return {"token": token, "ats": ats, "jobs": len(locs), "india_jobs": india}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=150)
    ap.add_argument("--refresh", action="store_true", help="re-verify every candidate")
    args = ap.parse_args()
    seen: set[str] = set()
    found: list[dict[str, Any]] = []
    todo = CANDIDATES + EXTRA_CANDIDATES
    if OUT.exists() and not args.refresh:
        # Incremental: keep verified boards, skip first-round tokens that already failed.
        found = (yaml.safe_load(OUT.read_text(encoding="utf-8")) or {}).get("companies", [])
        seen = {c["token"] for c in found} | set(CANDIDATES)
    with httpx.Client(headers=UA, follow_redirects=True) as client:
        for token in todo:
            if token in seen:
                continue
            seen.add(token)
            hit = probe(client, token)
            if hit:
                found.append(hit)
                print(f"OK  {token:<18} {hit['ats']:<10} jobs={hit['jobs']:<5} india={hit['india_jobs']}", flush=True)
    found.sort(key=lambda h: (h["india_jobs"] > 0, h["india_jobs"], h["jobs"]), reverse=True)
    kept = found[: args.target]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Verified public ATS job boards (Greenhouse / Lever / Ashby).\n"
        "# Generated by scripts/verify_companies.py; every token responded with open jobs.\n"
    )
    OUT.write_text(header + yaml.safe_dump({"companies": kept}, sort_keys=False), encoding="utf-8")
    print(f"verified={len(found)} kept={len(kept)} india_companies={sum(1 for h in kept if h['india_jobs'])} "
          f"total_jobs={sum(h['jobs'] for h in kept)} india_jobs={sum(h['india_jobs'] for h in kept)}")


if __name__ == "__main__":
    main()
