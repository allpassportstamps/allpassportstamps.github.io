(function () {
  'use strict';

  var page = document.querySelector('[data-search-index]');
  if (!page) return;
  var query = (new URLSearchParams(window.location.search).get('q') || '').trim();
  var status = page.querySelector('.search-status');
  var results = page.querySelector('.search-results');
  document.querySelectorAll('.search-form input').forEach(function (input) {
    input.value = query;
  });
  if (!query) {
    status.textContent = 'Enter a place, food, or experience to find posts.';
    return;
  }

  // Decode rendered article entities without interpreting them as page markup.
  function plainText(value) {
    var decoder = document.createElement('textarea');
    decoder.innerHTML = value.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return decoder.value.replace(/\s+/g, ' ').trim();
  }

  function excerpt(content, words) {
    var lower = content.toLowerCase();
    var positions = words.map(function (word) { return lower.indexOf(word); })
      .filter(function (position) { return position >= 0; });
    var start = positions.length ? Math.max(0, Math.min.apply(null, positions) - 65) : 0;
    if (start > 0) {
      var boundary = content.indexOf(' ', start);
      if (boundary >= 0 && boundary < start + 25) start = boundary + 1;
    }
    var end = Math.min(content.length, start + 220);
    if (end < content.length) {
      var lastSpace = content.lastIndexOf(' ', end);
      if (lastSpace > start) end = lastSpace;
    }
    return (start ? '…' : '') + content.slice(start, end) + (end < content.length ? '…' : '');
  }

  status.textContent = 'Searching posts…';
  fetch(page.dataset.searchIndex)
    .then(function (response) {
      if (!response.ok) throw new Error('Search index unavailable');
      return response.json();
    })
    .then(function (posts) {
      var words = Array.from(new Set(query.toLowerCase().split(/\s+/)));
      var matches = posts.map(function (post) {
        post.content = plainText(post.content);
        var title = post.title.toLowerCase();
        var tags = post.tags.join(' ').toLowerCase();
        var body = post.content.toLowerCase();
        return {
          post: post,
          matches: words.every(function (word) {
            return title.includes(word) || tags.includes(word) || body.includes(word);
          }),
          titleScore: words.filter(function (word) { return title.includes(word); }).length,
          tagScore: words.filter(function (word) { return tags.includes(word); }).length
        };
      }).filter(function (match) { return match.matches; });
      matches.sort(function (a, b) {
        return b.titleScore - a.titleScore || b.tagScore - a.tagScore ||
          b.post.date.localeCompare(a.post.date);
      });
      var fragment = document.createDocumentFragment();
      matches.forEach(function (match) {
        var post = match.post;
        var article = document.createElement('article');
        article.className = 'search-result';
        var heading = document.createElement('h2');
        var link = document.createElement('a');
        link.href = post.url;
        link.textContent = post.title;
        heading.appendChild(link);
        var date = document.createElement('time');
        date.dateTime = post.date;
        date.textContent = new Date(post.date + 'T00:00:00Z').toLocaleDateString('en-US', {
          year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC'
        });
        var summary = document.createElement('p');
        summary.textContent = excerpt(post.content, words);
        article.append(heading, date, summary);
        fragment.appendChild(article);
      });
      results.replaceChildren(fragment);
      status.textContent = matches.length ?
        matches.length + (matches.length === 1 ? ' post' : ' posts') + ' found for “' + query + '”.' :
        'No posts found for “' + query + '”. Try another place or keyword.';
    })
    .catch(function () {
      status.textContent = 'Search could not load. Please try again or browse My journey in the sidebar.';
    });
}());
