d = {'key': None}
val = d.get('key', 'default')
print(f"Value is: {val} (type: {type(val)})")

try:
    val[:10]
except Exception as e:
    print(f"Slicing None raises: {type(e).__name__}: {e}")
