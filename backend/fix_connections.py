import os

count = 0
for root, dirs, files in os.walk("apps"):
    for file in files:
        if file.startswith("tasks") and file.endswith(".py"):
            filepath = os.path.join(root, file)
            with open(filepath, "r") as f:
                content = f.read()
            
            # The replace logic
            if "    connection.close()" in content:
                content = content.replace(
                    "    # Mandatory Prevention Sweep (#86): close stale connections before task logic.\n    connection.close()",
                    "    # Mandatory Prevention Sweep (#86): close stale connections before task logic.\n    if not connection.in_atomic_block:\n        connection.close()"
                )
                # Fallback for any without the comment
                content = content.replace(
                    "\n    connection.close()\n",
                    "\n    if not connection.in_atomic_block:\n        connection.close()\n"
                )
                with open(filepath, "w") as f:
                    f.write(content)
                count += 1

print(f"Fixed {count} files.")
