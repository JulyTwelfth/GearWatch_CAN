document.querySelectorAll("[data-price-chart]").forEach((container) => {
  const values = (container.dataset.values || "")
    .split(",")
    .map(Number)
    .filter(Number.isFinite);

  if (values.length === 0) return;

  const width = 640;
  const height = 190;
  const padding = 24;
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const priceRange = maximum - minimum || 1;
  const step = values.length === 1 ? 0 : (width - padding * 2) / (values.length - 1);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : padding + index * step;
    const y = height - padding - ((value - minimum) / priceRange) * (height - padding * 2);
    return { x, y, value };
  });

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("chart-svg");

  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", points.map(({ x, y }) => `${x},${y}`).join(" "));
  line.setAttribute("class", "chart-line");
  svg.appendChild(line);

  points.forEach(({ x, y, value }) => {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", x);
    dot.setAttribute("cy", y);
    dot.setAttribute("r", "5");
    dot.setAttribute("class", "chart-dot");
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `$${value.toFixed(2)} CAD`;
    dot.appendChild(title);
    svg.appendChild(dot);
  });

  container.appendChild(svg);
});
