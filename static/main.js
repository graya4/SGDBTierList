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

              data.images.forEach(imageData => {
                const imgElement = document.createElement('img');
                imgElement.src = imageData.src;
                imgElement.alt = imageData.alt;

                // Restore playtime from JSON
                imgElement.dataset.hours = imageData.hours || "0";
                imgElement.dataset.minutes = imageData.minutes || "0";
                imgElement.dataset.seconds = imageData.seconds || "0";

                imgElement.draggable = true;
                imgElement.style.margin = '5px';
                imgElement.addEventListener('dragstart', handleDragStart);
                imgElement.addEventListener('dragend', handleDragEnd);
                imgElement.addEventListener('dblclick', handleImageRemove);
                itemsContainer.appendChild(imgElement);
              });


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



// Event listeners for the Save and Load buttons
document.getElementById('saveButton').addEventListener('click', saveTierList);
document.getElementById('loadButton').addEventListener('change', loadTierList);

document.getElementById('saveAsPngButton').addEventListener('click', () => {
  const tierListElement = document.querySelector('.tiers.container');
  const gameTitleContainer = document.querySelector('.game-title-container');
  const scrollContainer = document.getElementById('scroll-container');

  // List title
  const title = document.getElementById("tierListTitle").value.trim() || "Tier List";
  const titleElement = document.createElement('div');
  titleElement.textContent = title;
  titleElement.style.fontFamily = "'EB Garamond', serif";
  titleElement.style.fontSize = "48px";
  titleElement.style.color = "white";
  titleElement.style.fontWeight = 'bold';
  titleElement.style.textAlign = "center";
  titleElement.style.marginBottom = "30px";
  titleElement.style.width = "100%";



  // Quality scale
  const scale = parseFloat(document.getElementById("quality").value);

  // Show text toggle
  const showText = parseInt(document.getElementById("showTextToggle").value || "1");

  // Playtime toggle
  const showPlaytimes = parseInt(document.getElementById("showPlaytimeToggle").value || "1");

  // Hide UI elements
  const settingsModal = document.querySelector('.settings-modal');
  const controls = document.querySelector('.controls');
  settingsModal.style.display = 'none';
  if (controls) controls.style.display = 'none';
  scrollContainer.style.display = 'none';
  const buttons = document.querySelectorAll('button');
  buttons.forEach(button => button.style.display = 'none');

  const tiers = document.querySelectorAll('.tier');
  tiers.forEach(tier => {
    const excludeItems = tier.querySelectorAll('.exclude-item');
    excludeItems.forEach(item => item.style.display = 'none');
  });

  // Clone the tier list
  const tierListClone = tierListElement.cloneNode(true);
  tierListClone.style.pointerEvents = 'none';

  // Measure tier width
  const measureMaxWidth = (container) => {
    const temp = container.cloneNode(true);
    temp.style.position = 'absolute';
    temp.style.visibility = 'hidden';
    temp.style.width = 'fit-content';
    temp.style.whiteSpace = 'nowrap';
    document.body.appendChild(temp);
    const width = temp.offsetWidth;
    document.body.removeChild(temp);
    return width;
  };

  function getRenderedTierHeight(tierListClone) {
    const temp = tierListClone.cloneNode(true);
    temp.style.position = 'absolute';
    temp.style.visibility = 'hidden';
    temp.style.pointerEvents = 'none';
    temp.style.left = '-9999px';
    temp.style.top = '-9999px';

    document.body.appendChild(temp);
    const height = temp.offsetHeight;
    document.body.removeChild(temp);

    return height;
  }

  if (document.getElementById('showTextToggle').value === '0') {
    const tierWidth = measureMaxWidth(tierListElement);
    tierListClone.style.width = `${tierWidth}px`;
  }
  else {
    const tierWidth = measureMaxWidth(tierListElement) * 0.7;
    tierListClone.style.width = `${tierWidth}px`;
  }

  // Build title container only if showText === 1
  let columnizedTitleContainer = null;
  if (showText === 1) {
    const titleTextNodes = Array.from(gameTitleContainer.childNodes).filter(node => node.nodeType === Node.ELEMENT_NODE);
    const tempColumnWrapper = document.createElement('div');
    tempColumnWrapper.style.position = 'absolute';
    tempColumnWrapper.style.visibility = 'hidden';
    tempColumnWrapper.style.font = window.getComputedStyle(gameTitleContainer).font;
    titleTextNodes.forEach(node => {
      const clone = node.cloneNode(true);
      tempColumnWrapper.appendChild(clone);
    });
    document.body.appendChild(tempColumnWrapper);

    const tierHeight = getRenderedTierHeight(tierListClone);

    columnizedTitleContainer = document.createElement('div');
    columnizedTitleContainer.style.display = 'flex';
    columnizedTitleContainer.style.flexDirection = 'row';
    columnizedTitleContainer.style.color = '#D6BA8D';
    columnizedTitleContainer.style.fontFamily = 'monospace';
    columnizedTitleContainer.style.height = tierHeight + 'px';
    columnizedTitleContainer.style.overflow = 'hidden';

    let currentColumn = document.createElement('div');
    currentColumn.style.display = 'flex';
    currentColumn.style.flexDirection = 'column';
    currentColumn.style.marginRight = '40px';
    currentColumn.style.whiteSpace = 'nowrap';
    columnizedTitleContainer.appendChild(currentColumn);

    let currentHeight = 0;
    let oldNodeHeight;
    titleTextNodes.forEach(node => {
      console.log("CURRENT HEIGHT: " + currentHeight)
      console.log("TIER HEIGHT: " + tierHeight)
      console.log(node.textContent)
      console.log(node.offsetHeight)
      const clone = node.cloneNode(true);
      tempColumnWrapper.appendChild(clone);
      let nodeHeight = clone.offsetHeight;
      tempColumnWrapper.removeChild(clone);
      console.log("NODE HEIGHT: " + nodeHeight)
      console.log('----')

      if (nodeHeight === 0){
        nodeHeight = oldNodeHeight * 0.6
      }

    if (currentHeight + nodeHeight > tierHeight) {
      currentColumn = document.createElement('div');
      currentColumn.style.display = 'flex';
      currentColumn.style.flexDirection = 'column';
      currentColumn.style.marginRight = '40px';
      currentColumn.style.whiteSpace = 'nowrap';
      columnizedTitleContainer.appendChild(currentColumn);
      oldNodeHeight = nodeHeight;
      currentHeight = 0;
    }

    currentColumn.appendChild(node.cloneNode(true));
    currentHeight += nodeHeight;
    oldNodeHeight = nodeHeight;
    });

    document.body.removeChild(tempColumnWrapper);
  }

  // Hide playtimes in the cloned container if toggle is off
  if (showPlaytimes === 0 && columnizedTitleContainer) {
    const playtimeEls = columnizedTitleContainer.querySelectorAll('input[type="number"], span, #totalPlaytime');
    playtimeEls.forEach(el => {
      el.remove(); // strip them out entirely
    });
  }

  // Container for rendering
  // OUTER CONTAINER — vertical layout (title on its own row)
  const tempContainer = document.createElement('div');
  tempContainer.style.display = 'flex';
  tempContainer.style.flexDirection = 'column';  // ✅ Title sits ABOVE
  tempContainer.style.position = 'absolute';
  tempContainer.style.top = '-9999px';
  tempContainer.style.left = '-9999px';
  tempContainer.style.backgroundColor = '#1A1A17';
  tempContainer.style.padding = '6px';
  tempContainer.style.overflow = 'hidden';

  // Add TITLE first
  tempContainer.appendChild(titleElement);

  // INNER CONTAINER — horizontal layout for the actual list
  const rowWrapper = document.createElement('div');
  rowWrapper.style.display = 'flex';
  rowWrapper.style.flexDirection = 'row';  // ✅ List + columns side-by-side
  rowWrapper.style.alignItems = 'flex-start';
  rowWrapper.style.gap = '20px';  // optional, can remove

  // Add tier list and optional columnized titles
  rowWrapper.appendChild(tierListClone);
  if (showText === 1 && columnizedTitleContainer) {
    rowWrapper.appendChild(columnizedTitleContainer);
  }

  // Add rowWrapper under the title
  tempContainer.appendChild(rowWrapper);

  // Add tempContainer to document for rendering
  document.body.appendChild(tempContainer);


  // Render and download PNG
  html2canvas(tempContainer, {
    useCORS: true,
    scale: scale
  }).then((canvas) => {
    // Trim 1% off the right side
    const trimmedCanvas = document.createElement('canvas');
    const ctx = trimmedCanvas.getContext('2d');

    const trimAmount = 4;
    if (document.getElementById('showTextToggle').value === '0') {
      console.log(canvas.height)
      console.log(trimAmount)
      trimmedCanvas.height = canvas.height - trimAmount;
      trimmedCanvas.width = canvas.width;
    }
    else {
      console.log(canvas.width)
      console.log(trimAmount)
      trimmedCanvas.width = canvas.width - trimAmount;
      trimmedCanvas.height = canvas.height - trimAmount;
    }

    ctx.drawImage(canvas, 0, 0, trimmedCanvas.width, trimmedCanvas.height, 0, 0, trimmedCanvas.width, trimmedCanvas.height);

    const dataURL = trimmedCanvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.href = dataURL;
    const safeTitle = title.replace(/[^a-z0-9_\-]+/gi, "_");
    link.download = `${safeTitle}.png`;
    link.click();


    // Restore UI
    document.body.removeChild(tempContainer);
    scrollContainer.style.display = '';
    tierListElement.style.width = '';
    settingsModal.style.display = '';
    if (controls) controls.style.display = '';
    buttons.forEach(button => button.style.display = '');
    tiers.forEach(tier => {
      const excludeItems = tier.querySelectorAll('.exclude-item');
      excludeItems.forEach(item => item.style.display = '');
    });
  }).catch((error) => {
    console.error('Failed to capture and save as PNG:', error);
  });
});


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
