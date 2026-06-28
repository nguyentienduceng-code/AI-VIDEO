module.exports = {
  apps: [
    {
      name: "AI-Backend",
      script: "venv/Scripts/uvicorn.exe",
      args: "main:app --host 127.0.0.1 --port 8000",
      cwd: "./backend",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "development",
      }
    },
    {
      name: "AI-Frontend",
      script: "npm.cmd",
      args: "run dev -- --port 3001",
      cwd: "./frontend",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "development",
      }
    }
  ]
};
