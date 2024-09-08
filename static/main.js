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

function updateAltTextColorAndOrder() {
  const gameTitleContainer = document.querySelector('.game-title-container');
  gameTitleContainer.innerHTML = ''; // Clear existing titles

  // Iterate over each tier and collect the images and their alt texts
  const tiers = document.querySelectorAll('.tier');
  tiers.forEach(tier => {
      const tierColor = window.getComputedStyle(tier.querySelector('.label')).getPropertyValue('--color');
      const images = tier.querySelectorAll('.items img');
      
      images.forEach(image => {
          const altText = image.alt;
          const titleElement = document.createElement('p');
          titleElement.textContent = altText;
          titleElement.style.color = tierColor;
          titleElement.contentEditable = true; // Make the text editable
          titleElement.addEventListener('blur', () => handleTextEdit(titleElement, image)); // Add blur event to handle editing
          gameTitleContainer.appendChild(titleElement);
      });
  });
}

      // Function to extract the current state of the tier list and save it to a JSON file
function saveTierList() {
        const tierData = [];

        // Iterate over each tier to collect data
        const tiers = document.querySelectorAll('.tier');
        tiers.forEach(tier => {
            const tierName = tier.querySelector('.label span').textContent;
            const images = tier.querySelectorAll('.items img');
            const imageData = Array.from(images).map(img => ({
                src: img.src,
                alt: img.alt
            }));

            tierData.push({ tier: tierName, images: imageData });
        });

        // Create a JSON string from the collected data
        const jsonString = JSON.stringify(tierData);

        // Create a downloadable file
        const blob = new Blob([jsonString], { type: 'application/json' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'tier_list.json';
        link.click();
}

    // Function to load a tier list from a JSON file
function loadTierList(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
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
            tierData.forEach(data => {
                const tier = createTier(data.tier);
                const itemsContainer = tier.querySelector('.items');

                data.images.forEach(imageData => {
                    const imgElement = document.createElement('img');
                    imgElement.src = imageData.src;
                    imgElement.alt = imageData.alt;
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

    // Event listeners for the Save and Load buttons
    document.getElementById('saveButton').addEventListener('click', saveTierList);
    document.getElementById('loadButton').addEventListener('change', loadTierList);

    document.getElementById('saveAsPngButton').addEventListener('click', () => {
      // Select the containers you want to capture
      const tierListElement = document.querySelector('.tiers.container'); // Tier List container
      const gameTitleContainer = document.querySelector('.game-title-container'); // Game Title container
  
      // Create a temporary container to hold both elements
      const tempContainer = document.createElement('div');
      tempContainer.style.display = 'flex';
      tempContainer.style.flexDirection = 'row'; // Position elements side by side
      tempContainer.style.position = 'absolute'; // Position off-screen to avoid disrupting layout
      tempContainer.style.top = '-9999px';
      tempContainer.style.left = '-9999px';
      tempContainer.style.width = `${tierListElement.offsetWidth + gameTitleContainer.offsetWidth}px`; // Set width based on contents
      tempContainer.style.height = `${Math.max(tierListElement.offsetHeight, gameTitleContainer.offsetHeight)}px`; // Set height to the maximum height of the contents
  
      // Set the background color (change this to your desired color)
      tempContainer.style.backgroundColor = '#1A1A17'; // Light grey background color

      // Clone elements to ensure current state is captured
      const tierListClone = tierListElement.cloneNode(true);
      const gameTitleClone = gameTitleContainer.cloneNode(true);
  
      // Append clones to the temporary container
      tempContainer.appendChild(tierListClone);
      tempContainer.appendChild(gameTitleClone);
  
      // Append the temporary container to the body (hidden from view)
      document.body.appendChild(tempContainer);
  
      // Wait for images to load before capturing
      html2canvas(tempContainer, { useCORS: true, scale: 3 }).then((canvas) => {
          // Convert the canvas to a PNG data URL
          const dataURL = canvas.toDataURL('image/png');
  
          // Create a download link for the PNG
          const link = document.createElement('a');
          link.href = dataURL;
          link.download = 'tier_list.png';
          link.click();
  
          // Clean up: remove the temporary container
          document.body.removeChild(tempContainer);
      }).catch((error) => {
          console.error('Failed to capture and save as PNG:', error);
      });
  });
  
  

function handleTextEdit(titleElement, image) {
  // Update the alt text of the image with the new text
  const newAltText = titleElement.textContent;
  image.alt = newAltText;
}

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

//* event listeners

document.querySelector("h1").addEventListener("click", () => {
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
