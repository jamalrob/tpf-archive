(function () {
    var pagefindModule = null;

    async function loadPagefind() {
        if (pagefindModule) return pagefindModule;
        try {
            pagefindModule = await import('/pagefind/pagefind.js');
            return pagefindModule;
        } catch (e) {
            return null;
        }
    }

    async function performFullTextSearch() {
        var input = document.getElementById('fulltextInput');
        var resultsEl = document.getElementById('fulltextResults');
        var statsEl = document.getElementById('fulltextStats');
        var btn = document.getElementById('fulltextButton');

        var query = input.value.trim();
        if (!query) return;

        statsEl.textContent = 'Searching…';
        resultsEl.innerHTML = '';
        btn.disabled = true;

        var pf = await loadPagefind();
        btn.disabled = false;

        if (!pf) {
            statsEl.textContent = '';
            resultsEl.innerHTML = '<div class="no-results">Full-text search index not yet available. Run the build, then <code>npx pagefind --site build/static_archive</code>.</div>';
            return;
        }

        var search = await pf.search(query);

        if (search.results.length === 0) {
            statsEl.textContent = '';
            resultsEl.innerHTML = '<div class="no-results"><h3>No results found</h3><p>Try different search terms.</p></div>';
            return;
        }

        statsEl.textContent = 'Found ' + search.results.length + ' discussion' + (search.results.length === 1 ? '' : 's');

        await renderBatch(search.results, 0, 20, resultsEl, search.results.length);
    }

    async function renderBatch(allResults, offset, batchSize, container, total) {
        var batch = allResults.slice(offset, offset + batchSize);
        var loaded = await Promise.all(batch.map(function (r) { return r.data(); }));
        var newOffset = offset + batchSize;

        var existingMore = container.querySelector('.fulltext-load-more');
        if (existingMore) existingMore.remove();

        loaded.forEach(function (result) {
            var div = document.createElement('div');
            div.className = 'search-result';

            var excerptHtml = '';
            if (result.sub_results && result.sub_results.length > 0) {
                excerptHtml = result.sub_results.slice(0, 3).map(function (sub) {
                    return '<div class="fulltext-excerpt"><a href="' + sub.url + '">' + sub.excerpt + '</a></div>';
                }).join('');
            } else {
                excerptHtml = '<div class="fulltext-excerpt">' + result.excerpt + '</div>';
            }

            div.innerHTML =
                '<h3><a href="' + result.url + '">' + (result.meta.title || result.url) + '</a></h3>' +
                excerptHtml;
            container.appendChild(div);
        });

        if (newOffset < total) {
            var remaining = total - newOffset;
            var moreDiv = document.createElement('div');
            moreDiv.className = 'fulltext-load-more';
            moreDiv.innerHTML = '<button>Load more results (' + remaining + ' remaining)</button>';
            moreDiv.querySelector('button').addEventListener('click', async function () {
                moreDiv.querySelector('button').disabled = true;
                moreDiv.querySelector('button').textContent = 'Loading…';
                await renderBatch(allResults, newOffset, batchSize, container, total);
            });
            container.appendChild(moreDiv);
        }
    }

    function initTabs() {
        var tabs = document.querySelectorAll('.search-tab');
        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                tabs.forEach(function (t) {
                    t.classList.remove('active');
                    t.setAttribute('aria-selected', 'false');
                });
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');

                var panels = document.querySelectorAll('.search-tab-panel');
                panels.forEach(function (p) { p.hidden = true; });
                var target = document.getElementById('tab-' + tab.dataset.tab);
                if (target) target.hidden = false;
            });
        });
    }

    function initFullText() {
        var btn = document.getElementById('fulltextButton');
        var input = document.getElementById('fulltextInput');
        if (btn) btn.addEventListener('click', performFullTextSearch);
        if (input) input.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') performFullTextSearch();
        });
    }

    function init() {
        initTabs();
        initFullText();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
