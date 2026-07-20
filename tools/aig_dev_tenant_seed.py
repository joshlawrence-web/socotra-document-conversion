#!/usr/bin/env python3
"""Seed the aig-bsr-dev sandbox tenant with a test account + BlanketSpecialRisk quote.

Re-runnable: each run creates a fresh account + quote and prints their locators.
Every payload value is derived from workspace-prod/reference/socotra-config/
(constraint-table strings are byte-for-byte from the bootstrap CSVs).

Usage:
    python3 tools/aig_dev_tenant_seed.py

Credentials come from .env.ai-documents (AI_DOCUMENTS_API_URL / AI_DOCUMENTS_PAT).
The tenant locator is pinned below (NOT AI_DOCUMENTS_TENANT_LOCATOR — that is the
old ZenCover tenant).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TENANT = os.environ.get("AIG_DEV_TENANT_LOCATOR", "4a6c9ff6-3258-4fa0-a2d4-3959ac779580")


def load_env():
    env = {}
    with open(os.path.join(REPO, ".env.ai-documents")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("AI_DOCUMENTS_API_URL", "AI_DOCUMENTS_PAT"):
        env[k] = os.environ.get(k, env.get(k))
    return env


ENV = load_env()
API = ENV["AI_DOCUMENTS_API_URL"].rstrip("/")


def call(method, path, body=None, retries=6):
    """POST/GET with retry — the tenant's bootstrap may still be settling."""
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {ENV['AI_DOCUMENTS_PAT']}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            # ponytail: crude bootstrap-not-ready heuristic; retry 5xx and
            # anything mentioning bootstrap/deployment, else fail loud.
            transient = e.code >= 500 or "bootstrap" in detail.lower()
            if transient and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  transient {e.code}, retrying in {wait}s: {detail[:200]}", file=sys.stderr)
                time.sleep(wait)
                continue
            raise SystemExit(f"{method} {url} -> {e.code}\n{detail}")


ADDRESS = {  # dataTypes/Address — state is States.fullStateName ("New York", not "NY")
    "address1": "123 Test Street",
    "city": "New York",
    "state": "New York",
    "postalCode": "10001",
    "country": "United States",
    "addressType": "Street",
}

ACCOUNT_PAYLOAD = {
    "type": "PolicyholderData",  # accounts/PolicyholderData (displayName "Policyholder")
    "data": {
        "name": "Test Policyholder Inc",
        "policyHolderStreetAddress": ADDRESS,
        "manuallyCreated": True,
    },
}


def quote_payload(account_locator):
    return {
        "accountLocator": account_locator,
        "productName": "BlanketSpecialRisk",
        "timezone": "America/New_York",
        # requirement 6: explicit term so policyEffectiveDate/TerminationDate resolve
        "startTime": "2026-08-01T00:00:00Z",
        "endTime": "2027-08-01T00:00:00Z",
        "data": {
            "submissionDate": "2026-07-16",
            "totalEligiblelives": 100,
            "groupType": "Camps",  # StateGroupMapping row for New York
            "paymentPlan": "Fixed Premium",
            "paymentMode": "Paid Up Front",
            "minimumPremiumCalculation": {"minimumPremiumCalculation": "Not Book Of Business"},
            "policyHolder": {  # M1 template reads $data.quote.data.policyHolder.*
                "name": "Test Policyholder Inc",
                "policyHolderAddress": ADDRESS,
            },
            "producer": {},  # ProducerAssociation! — all subfields optional
            "product": {  # ProductHierarchy row (Day Camps)
                "market": "Specialty",
                "marketSegment": "Sports and Recreational Organizations",
                "marketSubSegment": "Camps -Day",
                "marketProduct": "Day Camps Participant Accident",
                "pucCode": "777",
                "pucDescription": "Participant Accident",
            },
            "claimsHandling": {  # TpaContactMapping row 1
                "claimstpa": "A-G Administrators",
                "claimsTpaContact": "Anthony Ciavardelli",
                "claimsTpaFee": 5,
            },
            "raterPreselect": "Standard BSR Experience Rater",
            "raterSelection": "Standard BSR Experience Rater",  # RaterSelection.csv valid pair
            "producerDetails": {"commissionRate": 15, "estimatedPremium": 10000},
        },
        "elements": [
            {
                "type": "Risk",
                "data": {
                    "number": 1,
                    # constrained to RiskClasses.riskClass — note the double space
                    "riskClass": "Class A  (Base Premium Factor = 0.02)",
                    "classDescription": "All enrolled participants of the Policyholder for whom premium has been paid.",
                    "selectTravelCoverage": "No",
                    "isWarRisk": "No",
                },
                "elements": [
                    {
                        "type": "AccidentalDeathAndDismemberment",
                        "coverageTerms": {"AccidentalDeathMaximumAmount": 50000},
                        "data": {
                            "accidentalDeath": {"accidentalDeathIncurralPeriod": "365 Days"},
                            "includeAccidentalDismemberment": "Yes",
                            "accidentalDismemberment": {
                                "dismembermentMaximumAmount": 50000,
                                "dismembermentIncurralPeriod": "365 Days",
                                "dismembermentSchedule": "Standard",
                            },
                            "reductionSchedule": {"includeReductionSchedule": "No"},
                        },
                    },
                    {
                        "type": "AccidentMedicalExpense",
                        "coverageTerms": {"AccidentMedicalExpenseAmount": 25000},
                        "data": {
                            "primaryOrExcessOrCoordinationOfBenefits": "Primary",
                            "benefitPeriodWeeks": "52 weeks",
                            "incurralPeriodDays": "90 Days",
                            "includeDeductible": "No",
                            "includeCoinsurance": "No",
                            "includeAggregateDeductible": "No",
                            "allowConditionsControlledByMedication": "Yes",
                        },
                    },
                    {
                        "type": "Coma",
                        "coverageTerms": {"ComaMaximumAmount": 10000},
                        "data": {"incurralPeriodDays": "90"},
                    },
                ],
            },
            {  # bare ref in product contents => required
                "type": "PermissibleLoss",
                "data": {
                    "initialEstimateOfPremium": 10000,
                    "priorYearCommissionRate": 10,
                    "proposedCommissionRate": 10,
                    "policyholderSitusStatePermissibleLossRatio": 50,
                    "operatingExpense": 10,
                    "inputTpa": "A-G Administrators",
                    "tpaClaimsAdjusterFee": 5,
                    "unallocatedLossAdjustmentExpense": 2,
                    "expenseRatio": 25,
                    "profitMargin": 5,
                    "expenseRatioPlusProfitMargin": 30,
                    "permissibleLossRatio": 70,
                },
            },
            {
                "type": "PolicyAdjustmentFactor",
                "data": {"includeModifiedPayment": "Yes", "allowForeignCurrencyPayment": "Yes"},
            },
            {
                "type": "GeneralExclusions",
                "data": {
                    "exclusions": {"removeDrugExclusion": "No", "removeAlcoholExclusion": "No"},
                    "exclusionsQuestionnaire": {},  # every field carries a defaultValue
                },
            },
            {"type": "Limitations", "data": {"includeLimitations": "Yes"}},
            {"type": "Injury", "data": {"injury": {"definitionChoice": "Yes"}}},
            {"type": "RightToTermination", "data": {"includePolicyholder30DayTerminationRight": "Yes"}},
            {"type": "BeneficiaryDetails", "data": {"allowBeneficiaryTree": "Yes"}},
        ],
    }


def main():
    print(f"tenant: {TENANT}")
    account = call("POST", f"/policy/{TENANT}/accounts", ACCOUNT_PAYLOAD)
    acct_loc = account["locator"]
    print(f"account locator: {acct_loc}")

    # quote create requires the account in validated state
    call("PATCH", f"/policy/{TENANT}/accounts/{acct_loc}/validate", {})
    print("account validated")

    quote = call("POST", f"/policy/{TENANT}/quotes", quote_payload(acct_loc))
    q_loc = quote["locator"]
    print(f"quote locator:   {q_loc}")

    # minimal lifecycle: validate + price ($0 expected — no RatePlugin deployed)
    call("PATCH", f"/policy/{TENANT}/quotes/{q_loc}/validate", {})
    priced = call("PATCH", f"/policy/{TENANT}/quotes/{q_loc}/price", {})
    print(f"quote state:     {priced.get('quoteState')}")
    print(json.dumps({"accountLocator": acct_loc, "quoteLocator": q_loc,
                      "quoteState": priced.get("quoteState")}, indent=2))


if __name__ == "__main__":
    main()
