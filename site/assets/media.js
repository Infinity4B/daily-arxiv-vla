/**
 * @file media.js
 * @description 通用论文图片灯箱：支持点击放大、滚轮缩放、拖拽查看和键盘关闭。
 */
(function(){
  let lightboxEl = null;
  let imageEl = null;
  let captionEl = null;
  let scaleLabelEl = null;
  let closeButtonEl = null;
  let imageScale = 1;
  let imageOffsetX = 0;
  let imageOffsetY = 0;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragOriginX = 0;
  let dragOriginY = 0;
  let activePointerId = null;
  let returnFocusEl = null;

  function clampScale(value){
    return Math.min(4, Math.max(1, value));
  }

  function renderTransform(){
    if(!imageEl || !scaleLabelEl){
      return;
    }

    imageEl.style.transform = `translate3d(${imageOffsetX}px, ${imageOffsetY}px, 0) scale(${imageScale})`;
    imageEl.classList.toggle('is-zoomed', imageScale > 1);
    scaleLabelEl.textContent = `${Math.round(imageScale * 100)}%`;
  }

  function setScale(nextScale){
    const normalizedScale = clampScale(nextScale);
    if(normalizedScale === 1){
      imageOffsetX = 0;
      imageOffsetY = 0;
    }
    imageScale = normalizedScale;
    renderTransform();
  }

  function resetImagePosition(){
    imageScale = 1;
    imageOffsetX = 0;
    imageOffsetY = 0;
    renderTransform();
  }

  function ensureLightbox(){
    if(lightboxEl){
      return;
    }

    lightboxEl = document.createElement('div');
    lightboxEl.className = 'image-lightbox';
    lightboxEl.setAttribute('aria-hidden', 'true');
    lightboxEl.innerHTML = `
      <div class="image-lightbox-stage" data-image-lightbox-close>
        <img class="image-lightbox-image" alt="" draggable="false" />
      </div>
      <div class="image-lightbox-topbar">
        <p class="image-lightbox-caption"></p>
        <button class="image-lightbox-close" type="button" aria-label="关闭图片预览">×</button>
      </div>
      <div class="image-lightbox-controls" aria-label="图片缩放控制">
        <button type="button" data-image-zoom-out aria-label="缩小图片">−</button>
        <button class="image-lightbox-scale" type="button" data-image-zoom-reset aria-label="恢复原始缩放">100%</button>
        <button type="button" data-image-zoom-in aria-label="放大图片">+</button>
      </div>
    `;

    document.body.appendChild(lightboxEl);
    imageEl = lightboxEl.querySelector('.image-lightbox-image');
    captionEl = lightboxEl.querySelector('.image-lightbox-caption');
    scaleLabelEl = lightboxEl.querySelector('.image-lightbox-scale');
    closeButtonEl = lightboxEl.querySelector('.image-lightbox-close');
    const stageEl = lightboxEl.querySelector('.image-lightbox-stage');

    lightboxEl.addEventListener('click', (event) => {
      if(event.target.closest('[data-image-lightbox-close]') && event.target !== imageEl){
        close();
      }
    });

    closeButtonEl.addEventListener('click', close);
    lightboxEl.querySelector('[data-image-zoom-out]').addEventListener('click', () => setScale(imageScale - 0.5));
    lightboxEl.querySelector('[data-image-zoom-in]').addEventListener('click', () => setScale(imageScale + 0.5));
    lightboxEl.querySelector('[data-image-zoom-reset]').addEventListener('click', resetImagePosition);

    stageEl.addEventListener('wheel', (event) => {
      if(!lightboxEl.classList.contains('is-open')){
        return;
      }
      event.preventDefault();
      setScale(imageScale + (event.deltaY < 0 ? 0.25 : -0.25));
    }, { passive: false });

    imageEl.addEventListener('dblclick', () => {
      setScale(imageScale > 1 ? 1 : 2);
    });

    imageEl.addEventListener('pointerdown', (event) => {
      if(imageScale <= 1){
        return;
      }
      activePointerId = event.pointerId;
      dragStartX = event.clientX;
      dragStartY = event.clientY;
      dragOriginX = imageOffsetX;
      dragOriginY = imageOffsetY;
      imageEl.setPointerCapture(event.pointerId);
      imageEl.classList.add('is-dragging');
    });

    imageEl.addEventListener('pointermove', (event) => {
      if(activePointerId !== event.pointerId){
        return;
      }
      imageOffsetX = dragOriginX + event.clientX - dragStartX;
      imageOffsetY = dragOriginY + event.clientY - dragStartY;
      renderTransform();
    });

    function stopDragging(event){
      if(activePointerId !== event.pointerId){
        return;
      }
      activePointerId = null;
      imageEl.classList.remove('is-dragging');
    }

    imageEl.addEventListener('pointerup', stopDragging);
    imageEl.addEventListener('pointercancel', stopDragging);

    window.addEventListener('keydown', (event) => {
      if(!lightboxEl.classList.contains('is-open')){
        return;
      }
      if(event.key === 'Escape'){
        event.preventDefault();
        close();
      }
      if(event.key === '+' || event.key === '='){
        setScale(imageScale + 0.5);
      }
      if(event.key === '-'){
        setScale(imageScale - 0.5);
      }
    });
  }

  function open(options){
    if(!options || !options.src){
      return;
    }

    ensureLightbox();
    returnFocusEl = options.returnFocus || document.activeElement;
    imageEl.src = options.src;
    imageEl.alt = options.alt || '论文图片放大预览';
    captionEl.textContent = options.caption || options.alt || '';
    captionEl.classList.toggle('hidden', !captionEl.textContent);
    resetImagePosition();
    lightboxEl.classList.add('is-open');
    lightboxEl.setAttribute('aria-hidden', 'false');
    document.body.classList.add('has-image-lightbox');
    window.requestAnimationFrame(() => closeButtonEl.focus());
  }

  function close(){
    if(!lightboxEl || !lightboxEl.classList.contains('is-open')){
      return;
    }

    lightboxEl.classList.remove('is-open');
    lightboxEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('has-image-lightbox');
    imageEl.removeAttribute('src');
    if(returnFocusEl && typeof returnFocusEl.focus === 'function'){
      returnFocusEl.focus({ preventScroll: true });
    }
    returnFocusEl = null;
  }

  function isOpen(){
    return Boolean(lightboxEl && lightboxEl.classList.contains('is-open'));
  }

  window.PaperImageViewer = { open, close, isOpen };
})();