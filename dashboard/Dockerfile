# CortexDB Dashboard - Placeholder (build with Next.js/React)
FROM node:20-alpine
WORKDIR /app
RUN echo '{"name":"cortexdb-dashboard","version":"2.0.0","scripts":{"start":"npx serve -s build -l 3000"}}' > package.json
RUN mkdir build && echo '<html><head><title>CortexDB Dashboard</title><style>body{font-family:Arial;background:#0a1628;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}div{text-align:center}h1{font-size:3em;background:linear-gradient(135deg,#2E86C1,#27AE60);-webkit-background-clip:text;-webkit-text-fill-color:transparent}p{color:#888;font-size:1.2em}a{color:#2E86C1}</style></head><body><div><h1>CortexDB</h1><p>Dashboard v2.0 - Coming Soon</p><p>API: <a href="/health/deep">Health</a> | <a href="/v1/asa/standards">Standards</a> | <a href="/admin/cache/stats">Cache</a></p><p style="margin-top:2em;font-size:0.9em;color:#555">(c) 2026 Nirlab Inc.</p></div></body></html>' > build/index.html
RUN npx serve --version || npm install -g serve
EXPOSE 3000
CMD ["npx", "serve", "-s", "build", "-l", "3000"]
