from jugaad_data.nse import NSELive

n = NSELive()
data = n.index_option_chain("NIFTY")

records = data.get("records", {})
print(f"Underlying: {records.get('underlyingValue')}")
print(f"Expiry dates: {records.get('expiryDates')}")
print(f"Total strikes: {len(records.get('data', []))}")

# Show first strike as sample
if records.get("data"):
    print("\nSample record:")
    print(records["data"][0])
