# Django Query Builder

A standalone vanilla HTML, CSS, and JavaScript interface for composing complex Django `Q` object queries without writing code.

## Getting Started

- Open `index.html` directly in your browser, or
- Serve the folder with any static file server (for example `python3 -m http.server`).

No build tools or package managers are required.

## Features

- Nested groups with `AND`/`OR` logical operators
- Optional `NOT` modifiers at both group and condition levels
- Rich field and operator selectors
- Live readable preview and Django ORM (`Q` objects) output

## Project Structure

- `index.html` – Page markup and layout shell
- `styles.css` – Theme and component styling (ported from the original Tailwind design)
- `main.js` – Query builder logic and DOM rendering
- `public/` – Static assets such as the favicon

Feel free to adapt the styles or extend the JavaScript logic to integrate with your backend of choice.
