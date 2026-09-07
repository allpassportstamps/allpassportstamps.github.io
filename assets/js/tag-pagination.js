(function () {
  'use strict';

  var pageSize = 5;

  document.querySelectorAll('[data-tag-pagination]').forEach(function (group) {
    var posts = Array.from(group.querySelectorAll('.tag-list'));
    var totalPages = Math.ceil(posts.length / pageSize);
    if (totalPages <= 1) return;

    var tagName = group.querySelector('h2').textContent;
    var postList = group.querySelector('.tag-posts');
    var currentPage = 1;
    var nav = document.createElement('nav');
    nav.className = 'pagination tag-pagination';
    nav.setAttribute('aria-label', tagName + ' post pages');
    var list = document.createElement('ul');
    nav.appendChild(list);
    var status = document.createElement('span');
    status.className = 'tag-pagination-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-atomic', 'true');
    nav.appendChild(status);
    group.appendChild(nav);

    function addItem(element) {
      var item = document.createElement('li');
      item.appendChild(element);
      list.appendChild(item);
    }

    function addButton(page, label, className, key, direction) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = className;
      button.dataset.key = key;
      button.setAttribute('aria-label', label);
      button.disabled = page < 1 || page > totalPages;
      if (button.disabled) button.classList.add('disabled');
      if (direction) {
        var icon = document.createElement('i');
        icon.className = 'fa fa-long-arrow-' + direction;
        icon.setAttribute('aria-hidden', 'true');
        button.appendChild(icon);
      } else {
        button.textContent = page;
        if (page === currentPage) {
          button.classList.add('current');
          button.setAttribute('aria-current', 'page');
        }
      }
      button.addEventListener('click', function () {
        currentPage = page;
        render();
        var nextFocus = list.querySelector('[data-key="' + key + '"]');
        if (!nextFocus || nextFocus.disabled) {
          nextFocus = list.querySelector('[aria-current="page"]');
        }
        nextFocus.focus({ preventScroll: true });
      });
      addItem(button);
    }

    function addPage(page) {
      addButton(page, tagName + ': page ' + page, 'page-number', 'page-' + page);
    }

    function addEllipsis() {
      var ellipsis = document.createElement('span');
      ellipsis.className = 'page-number';
      ellipsis.textContent = '…';
      ellipsis.setAttribute('aria-hidden', 'true');
      addItem(ellipsis);
    }

    function render() {
      var offset = (currentPage - 1) * pageSize;
      posts.forEach(function (post, index) {
        post.hidden = index < offset || index >= offset + pageSize;
      });
      list.replaceChildren();
      addButton(currentPage - 1, tagName + ': previous page', 'newer-posts', 'previous', 'left');
      var start = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
      var end = Math.min(totalPages, start + 4);
      if (start > 1) {
        addPage(1);
        if (start > 2) addEllipsis();
      }
      for (var page = start; page <= end; page++) addPage(page);
      if (end < totalPages) {
        if (end < totalPages - 1) addEllipsis();
        addPage(totalPages);
      }
      addButton(currentPage + 1, tagName + ': next page', 'older-posts', 'next', 'right');
      status.textContent = tagName + ': page ' + currentPage + ' of ' + totalPages;
    }

    // Measure every page at the current width, including wrapped titles.
    // Reserve the tallest page's height so shorter pages cannot move later tags.
    function reserveHeight() {
      posts.forEach(function (post) { post.hidden = false; });
      var tallestPage = 0;
      for (var offset = 0; offset < posts.length; offset += pageSize) {
        var pageHeight = posts.slice(offset, offset + pageSize).reduce(function (height, post) {
          return height + post.getBoundingClientRect().height;
        }, 0);
        tallestPage = Math.max(tallestPage, pageHeight);
      }
      postList.style.minHeight = Math.ceil(tallestPage) + 'px';
      posts.forEach(function (post, index) {
        post.hidden = index < (currentPage - 1) * pageSize || index >= currentPage * pageSize;
      });
    }

    reserveHeight();
    render();
    var lastWidth = group.getBoundingClientRect().width;
    var observer = new ResizeObserver(function () {
      var width = group.getBoundingClientRect().width;
      if (width !== lastWidth) {
        lastWidth = width;
        reserveHeight();
      }
    });
    observer.observe(group);
    if (document.fonts) document.fonts.ready.then(reserveHeight);
  });
}());
