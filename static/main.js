import { colors } from "./colors.js";

const settingsModal = document.querySelector(".settings-modal");
const colorsContainer = settingsModal.querySelector(".colors");
const tiersContainer = document.querySelector(".tiers");

let activeTier;

const resetTierImages = (tier) => {
  const images = tier.querySelectorAll(".items img");
  images.forEach((img) => {
    document.querySelector(".cards").appendChild(img);
  });
};

const handleDeleteTier = () => {
  if (activeTier) {
    resetTierImages(activeTier);
    activeTier.remove();
    settingsModal.close();
  }
};

const handleClearTier = () => {
  if (activeTier) {
    resetTierImages(activeTier);
    settingsModal.close();
  }
};

const handlePrependTier = () => {
  if (activeTier) {
    tiersContainer.insertBefore(createTier(), activeTier);
    settingsModal.close();
  }
};

const handleAppendTier = () => {
  if (activeTier) {
    tiersContainer.insertBefore(createTier(), activeTier.nextSibling);
    settingsModal.close();
  }
};

const handleSettingsClick = (tier) => {
  activeTier = tier;

  // populate the textarea
  const label = tier.querySelector(".label");
  settingsModal.querySelector(".tier-label").value = label.innerText;

  // select the color
  const color = getComputedStyle(label).getPropertyValue("--color");
  settingsModal.querySelector(`input[value="${color}"]`).checked = true;

  settingsModal.showModal();
};

const handleMoveTier = (tier, direction) => {
  const sibling =
    direction === "up" ? tier.previousElementSibling : tier.nextElementSibling;

  if (sibling) {
    const position = direction === "up" ? "beforebegin" : "afterend";
    sibling.insertAdjacentElement(position, tier);
  }
};

function handleDragStart(event) {
  event.dataTransfer.setData('text/plain', event.target.src);
  event.target.classList.add('dragging');
}

function handleDragEnd(event) {
  event.target.classList.remove('dragging');
}

function handleDragover(event) {
  event.preventDefault(); // Allow drop
}

function handleDrop(event) {
  event.preventDefault(); // Prevent default browser handling

  const draggedImage = document.querySelector('.dragging');
  if (!draggedImage) {
      console.error('No image is being dragged.');
      return;
  }

  const target = event.target;
  if (target.classList.contains("items")) {
      target.appendChild(draggedImage);
      updateAltTextColorAndOrder();
  } else if (target.tagName === "IMG" && target !== draggedImage) {
      const { left, width } = target.getBoundingClientRect();
      const midPoint = left + width / 2;

      if (event.clientX < midPoint) {
          target.before(draggedImage);
      } else {
          target.after(draggedImage);
      }
      updateAltTextColorAndOrder();
  }
}

function handleImageRemove(event) {
  // Remove the image from the tier
  const image = event.target;
  image.remove();

  // Update the alt text in the game-title-container
  updateAltTextColorAndOrder();
}

// Function to extract the current state of the tier list and save it to a JSON file
function saveTierList() {
  const tierData = [];

  // Iterate over each tier to collect data
  const tiers = document.querySelectorAll('.tier');
  tiers.forEach(tier => {
      const tierName = tier.querySelector('.label span').textContent;
      const tierColor = getComputedStyle(tier.querySelector('.label')).getPropertyValue('--color');
      const images = tier.querySelectorAll('.items img');
      const imageData = Array.from(images).map(img => ({
          src: img.src,
          alt: img.alt,
          hours: img.dataset.hours || "0",
          minutes: img.dataset.minutes || "0",
          seconds: img.dataset.seconds || "0"
      }));

      tierData.push({ 
          tier: tierName, 
          color: tierColor, // Include color information
          images: imageData 
      });
  });

  // Create a JSON string from the collected data
  const jsonString = JSON.stringify(tierData);

  // Create a downloadable file
  const blob = new Blob([jsonString], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  const title = document.getElementById("tierListTitle")?.value.trim() || "tier_list";
  const safeTitle = title.replace(/[^a-z0-9_\-]+/gi, "_");
  link.download = `${safeTitle}.json`;
  link.click();
}

function loadTierList(event) {
  const file = event.target.files[0];
  event.target.value = '';  // allow re-loading the same file
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function (e) {
      const jsonString = e.target.result;

      try {
          const tierData = JSON.parse(jsonString);

          // Check if the loaded data is valid
          if (!Array.isArray(tierData) || tierData.length === 0) {
              alert('The tier list is empty or the file format is invalid.');
              return;
          }

          // Clear existing tiers only if they are present
          if (tiersContainer.children.length > 0) {
              tiersContainer.innerHTML = '';
          }

          // Recreate tiers and their images based on the loaded data
          tierData.forEach((data, index) => {
              const tier = createTier(data.tier);
              const itemsContainer = tier.querySelector('.items');

              // Check if the color information exists; if not, use a default or calculated color
              const tierColor = data.color || colors[index % colors.length]; // Use provided color or fallback to a default
              const label = tier.querySelector('.label');
              label.style.setProperty('--color', tierColor);

              const fragment = document.createDocumentFragment();
              (data.images || []).forEach(imageData => {
                if (!imageData || !imageData.src) return;
                const imgElement = document.createElement('img');
                imgElement.alt = imageData.alt || '';
                imgElement.decoding = 'async';

                // Restore playtime from JSON
                imgElement.dataset.hours = imageData.hours || "0";
                imgElement.dataset.minutes = imageData.minutes || "0";
                imgElement.dataset.seconds = imageData.seconds || "0";

                imgElement.draggable = true;
                imgElement.style.margin = '5px';
                imgElement.addEventListener('dragstart', handleDragStart);
                imgElement.addEventListener('dragend', handleDragEnd);
                imgElement.addEventListener('dblclick', handleImageRemove);
                window.attachImageRetry?.(imgElement);  // retry transient failures
                imgElement.src = imageData.src;           // set last so error handler is ready
                fragment.appendChild(imgElement);
              });
              itemsContainer.appendChild(fragment);


                tiersContainer.appendChild(tier);
              });

              updateAltTextColorAndOrder();


      } catch (error) {
          alert('Failed to load the tier list. The file might be corrupted or in an invalid format.');
          console.error('Error parsing JSON:', error);
      }
  };

  reader.readAsText(file);
}


function listRoulette(){
    const tierData = [];

    const tiers = document.querySelectorAll('.tier');
    tiers.forEach(tier => {
        const tierName = tier.querySelector('.label span').textContent;
        const tierColor = getComputedStyle(tier.querySelector('.label')).getPropertyValue('--color');
        const images = tier.querySelectorAll('.items img');
        const imageData = Array.from(images).map(img => ({
            src: img.src,
            alt: img.alt
        }));

        tierData.push({ 
            tier: tierName, 
            color: tierColor, 
            images: imageData 
        });
    });

    const jsonString = JSON.stringify(tierData);

    fetch("/roulette_choose", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: jsonString
    })
    .then(response => {
        if (!response.ok) {
            throw new Error("Network response was not ok");
        }
        return response.blob();
    })
    .then(blob => {
        const imgUrl = URL.createObjectURL(blob);
        const resultImg = document.getElementById("resultImage");
        resultImg.src = imgUrl;
        resultImg.style.display = "block";
    })
    .catch(err => {
        console.error("Fetch error:", err);
    });
}

document.getElementById("roulette").addEventListener("click", listRoulette);



// Rewrites every proxied image (".../proxy?url=...") to point at a new server origin.
// Saved lists store absolute proxy URLs, so a list saved on one host breaks on another.
function rewriteProxyServer(newServer) {
  let origin;
  try {
    origin = new URL(newServer.trim()).origin;
  } catch {
    return null;
  }

  let changed = 0;
  document.querySelectorAll('.tier .items img').forEach(img => {
    let current;
    try {
      current = new URL(img.src, window.location.href);
    } catch {
      return;
    }
    if (current.pathname !== '/proxy' || !current.searchParams.has('url')) return;

    const updated = `${origin}/proxy?url=${encodeURIComponent(current.searchParams.get('url'))}`;
    if (img.src !== updated) {
      img.src = updated;
      changed++;
    }
  });
  return { origin, changed };
}

const proxyServerInput = document.getElementById('proxyServerInput');
const proxyServerStatus = document.getElementById('proxyServerStatus');
proxyServerInput.value = window.location.origin;

document.getElementById('proxyServerButton').addEventListener('click', () => {
  const result = rewriteProxyServer(proxyServerInput.value);
  if (!result) {
    proxyServerStatus.textContent = 'Invalid address — include http:// or https://';
    return;
  }
  proxyServerInput.value = result.origin;
  proxyServerStatus.textContent = `Updated ${result.changed} image(s) to ${result.origin}`;
});

// Event listeners for the Save and Load buttons
document.getElementById('saveButton').addEventListener('click', saveTierList);
document.getElementById('loadButton').addEventListener('change', loadTierList);

// Render on the server so browser extensions (injected CSS, dark-mode
// filters, overlays, canvas noise) can't affect the output.
function buildRenderPayload() {
  const tiers = Array.from(document.querySelectorAll('.tier')).map(tier => ({
    tier: tier.querySelector('.label span').textContent,
    color: getComputedStyle(tier.querySelector('.label')).getPropertyValue('--color').trim(),
    images: Array.from(tier.querySelectorAll('.items img')).map(img => ({
      src: img.src,
      alt: img.alt,
      hours: img.dataset.hours || "0",
      minutes: img.dataset.minutes || "0",
      seconds: img.dataset.seconds || "0"
    }))
  }));

  return {
    title: document.getElementById("tierListTitle").value.trim() || "Tier List",
    format: document.getElementById("imageFormat")?.value || "png",
    scale: parseFloat(document.getElementById("quality").value) || 2,
    showText: parseInt(document.getElementById("showTextToggle").value || "1"),
    showPlaytimes: parseInt(document.getElementById("showPlaytimeToggle").value || "1"),
    showOdds: parseInt(document.getElementById("showOddsToggle")?.value || "0"),
    tiers
  };
}

// ---- Roulette odds (same weights the server uses to pick) ----
let oddsSeq = 0;

async function updateRouletteOdds() {
  const table = document.getElementById('rouletteOddsTable');
  const empty = document.getElementById('rouletteOddsEmpty');
  if (!table) return;
  const tiers = buildRenderPayload().tiers.map(t => ({ tier: t.tier, color: t.color, images: t.images }));
  const seq = ++oddsSeq;
  try {
    const response = await fetch('/roulette_odds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tiers })
    });
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    const { odds } = await response.json();
    if (seq !== oddsSeq) return;

    const hasGames = odds.some(o => o.count > 0);
    table.style.display = hasGames ? '' : 'none';
    empty.style.display = hasGames ? 'none' : '';

    const tbody = table.querySelector('tbody');
    tbody.replaceChildren(...odds.map(o => {
      const tr = document.createElement('tr');
      if (!o.count) tr.className = 'empty';
      tr.style.setProperty('--tier-color', o.color);
      const cells = [
        o.tier || '(unnamed)',
        String(o.count),
        o.count ? `${(o.perGame * 100).toFixed(2)}%` : '—',
        o.count ? `${(o.tierTotal * 100).toFixed(1)}%` : '—'
      ];
      cells.forEach(text => {
        const td = document.createElement('td');
        td.textContent = text;
        tr.appendChild(td);
      });
      return tr;
    }));
  } catch (error) {
    if (seq === oddsSeq) console.error('Odds update failed:', error);
  }
}

const EXTENSIONS = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' };

async function renderTierListImage() {
  const button = document.getElementById('saveAsPngButton');
  const payload = buildRenderPayload();

  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = 'Rendering...';
  try {
    const response = await fetch('/render_png', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`Server returned ${response.status}`);

    const blob = await response.blob();
    // Use the type the server actually produced (WebP falls back to PNG when too large)
    const extension = EXTENSIONS[blob.type] || 'png';
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${payload.title.replace(/[^a-z0-9_\-]+/gi, "_")}.${extension}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    console.error('Failed to render image:', error);
    alert('Failed to render the image. Check the server console for details.');
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

// ---- Predicted output size (layout-only estimate from the server) ----
function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

let estimateTimer = null;
let estimateSeq = 0;

async function updateRenderEstimate() {
  const el = document.getElementById('renderEstimate');
  if (!el) return;
  const payload = buildRenderPayload();
  if (!payload.tiers.some(t => t.images.length)) {
    el.textContent = 'Estimated size: add some games first';
    return;
  }
  const seq = ++estimateSeq;
  try {
    const response = await fetch('/render_estimate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    const est = await response.json();
    if (seq !== estimateSeq) return;  // a newer request superseded this one
    const requested = payload.format === 'jpeg' ? 'jpg' : payload.format;
    const fallback = est.format !== requested ? ` (too large for ${requested.toUpperCase()}, will be ${est.format.toUpperCase()})` : '';
    el.textContent = `Estimated size: ~${formatBytes(est.bytes)} · ${est.width} × ${est.height} px${fallback}`;
  } catch (error) {
    if (seq === estimateSeq) el.textContent = 'Estimated size: unavailable';
    console.error('Estimate failed:', error);
  }
}

// Called whenever the list or render options change; refreshes both the size
// estimate and the roulette odds table.
function scheduleRenderEstimate() {
  clearTimeout(estimateTimer);
  estimateTimer = setTimeout(() => {
    updateRenderEstimate();
    updateRouletteOdds();
  }, 400);
}
window.scheduleRenderEstimate = scheduleRenderEstimate;

['quality', 'imageFormat', 'showTextToggle', 'showPlaytimeToggle', 'showOddsToggle'].forEach(id =>
  document.getElementById(id)?.addEventListener('change', scheduleRenderEstimate));
document.getElementById('tierListTitle')?.addEventListener('input', scheduleRenderEstimate);
document.querySelector('.tab[data-tab="tab3"]')?.addEventListener('click', scheduleRenderEstimate);
document.querySelector('.tab[data-tab="tab4"]')?.addEventListener('click', scheduleRenderEstimate);

document.getElementById('saveAsPngButton').addEventListener('click', renderTierListImage);


const createTier = (label = "Change me") => {
  const tierColor = colors[tiersContainer.children.length % colors.length];

  const tier = document.createElement("div");
  tier.className = "tier";
  tier.innerHTML = `
  <div class="label" contenteditable="plaintext-only" style="--color: ${tierColor}">
    <span>${label}</span>
  </div>
  <div class="items"></div>
  <div class="controls">
    <button class="settings"><i class="bi bi-gear-fill"></i></button>
    <button class="moveup"><i class="bi bi-chevron-up"></i></button>
    <button class="movedown"><i class="bi bi-chevron-down"></i></button>
  </div>`;

  // Attach event listeners
  tier
    .querySelector(".settings")
    .addEventListener("click", () => handleSettingsClick(tier));
  tier
    .querySelector(".moveup")
    .addEventListener("click", () => handleMoveTier(tier, "up"));
  tier
    .querySelector(".movedown")
    .addEventListener("click", () => handleMoveTier(tier, "down"));
  tier.querySelector(".items").addEventListener("dragover", handleDragover);
  tier.querySelector(".items").addEventListener("drop", handleDrop);

  return tier;
};

const initColorOptions = () => {
  colors.forEach((color) => {
    const label = document.createElement("label");
    label.style.setProperty("--color", color);
    label.innerHTML = `<input type="radio" name="color" value="${color}" />`;
    colorsContainer.appendChild(label);
  });
};

const initDefaultTierList = () => {
  ["S", "A", "B", "C", "D"].forEach((label) => {
    tiersContainer.appendChild(createTier(label));
  });
};

const initDraggables = () => {
  const images = document.querySelectorAll(".cards img");
  images.forEach((img) => {
    img.draggable = true;

    img.addEventListener("dragstart", () => img.classList.add("dragging"));
    img.addEventListener("dragend", () => img.classList.remove("dragging"));
  });
};

initDraggables();
initDefaultTierList();
initColorOptions();

document.addEventListener('DOMContentLoaded', () => {
  const scrollContainer = document.getElementById('scroll-container');
  const imageUrls = []; // Add your image URLs here
  let currentIndex = 0;
  const imagesPerPage = 9;

  // Function to load images
  const loadImages = () => {
    const fragment = document.createDocumentFragment();
    const endIndex = Math.min(currentIndex + imagesPerPage, imageUrls.length);
    
    for (let i = currentIndex; i < endIndex; i++) {
      const img = document.createElement('img');
      img.src = imageUrls[i];
      img.className = 'image';
      fragment.appendChild(img);
    }

    scrollContainer.appendChild(fragment);
    currentIndex = endIndex;
  };

  // Debounce function to limit the rate of function execution
  const debounce = (func, delay) => {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => func.apply(this, args), delay);
    };
  };

  // Optimized scroll event listener with debouncing
  scrollContainer.addEventListener('scroll', debounce(() => {
    if (scrollContainer.scrollTop + scrollContainer.clientHeight >= scrollContainer.scrollHeight - 100) {
      if (currentIndex < imageUrls.length) {
        loadImages();
      }
    }
  }, 200));

  // Initial load of images
  loadImages();
});

document.querySelector("h2").addEventListener("click", () => {
  tiersContainer.appendChild(createTier());
});

settingsModal.addEventListener("click", (event) => {
  // if the clicked element is the settings modal then close it
  if (event.target === settingsModal) {
    settingsModal.close();
  } else {
    const action = event.target.id;
    const actionMap = {
      delete: handleDeleteTier,
      clear: handleClearTier,
      prepend: handlePrependTier,
      append: handleAppendTier,
    };

    if (action && actionMap[action]) {
      actionMap[action]();
    }
  }
});

settingsModal.addEventListener("close", () => (activeTier = null));

settingsModal
  .querySelector(".tier-label")
  .addEventListener("input", (event) => {
    if (activeTier) {
      activeTier.querySelector(".label span").textContent = event.target.value;
    }
  });

colorsContainer.addEventListener("change", (event) => {
  if (activeTier) {
    activeTier
      .querySelector(".label")
      .style.setProperty("--color", event.target.value);
  }
});
