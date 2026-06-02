std = "luajit"

ignore = {
  "212/_.*",
  "211",
}

globals = {
  "xf",
  "describe", "it", "before_each", "after_each",
  "assert",
  "property",
  "ngx",
}

files["frontend/nginx-lua/**/*.lua"] = {
  globals = {"ngx"},
}

files["**/tests/**/*.lua"] = {
  std = "luajit+busted",
}

exclude_files = {
  "**/node_modules/**",
  "**/.luarocks/**",
  "**/dist/**",
}
