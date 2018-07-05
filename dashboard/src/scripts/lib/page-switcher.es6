import $ from 'jquery';

/*
    class PageSwitcher
    - a class that handles 'tabbed' navigation
    - this class will be traversible and highly configurable using hooks (will improve overall page performance)
    - For now I'll try what I can do to optimize this page by de-initializing modules that are not visible.
    default pageswitcher html structure:

    <div class="page-switcher">
        <nav class="page-switcher__nav">
            <a href="page-switcher-page-1" class="active">page 1</a>
            <a href="page-switcher-page-2">page 2</a>
        </nav>
        <div class="page-switcher__pages">
            <div id="page-switcher-page-1" class="active">content for page 1</div>
            <div id="page-switcher-page-2">content for page 2</div>
        </div>
    </div>

 */
export default class PageSwitcher {

  constructor(options) {

    this.nav = options.nav;
    this.container = options.container;

    this.pages = [];

    this.events = $.extend({
      transition: function() {},
      beforeTransition: function() {},
      afterTransition: function() {}
    }, options.events ? options.events : {});

    this.initialise();
  }

  /*
        Called on instance construction
     */
  initialise() {

    var _this = this;

    this.indexPages();

    this.nav.find('a').bind('click', function(e) {
      e.preventDefault();
      _this._beforeTransition($(this));
    });

  }

  /*
        Creates a short summary about the pages and their names
     */
  indexPages() {
    var _this = this;
    this.container.children('div').each(function(i) {
      _this.pages.push({index: i, name: $(this).attr('id'), el: $(this), initialised: false});
    });
  }

  /*
        Prepares a transition
        - a transition is traversing from page A to page B
     */
  _beforeTransition(el) {

    var name = el.attr('href').replace('#', '');
    var targetPage;

    if (this.exists(name)) {
      this.nav.find('a').removeClass('active');
      this.container.children('div').removeClass('active');

      targetPage = this.getPage(name);

      this.events.beforeTransition.apply(this, [name, targetPage]);
      this._transition(targetPage, el);
    } else {
      this._afterTransition();
    }

  }

  /*
        Executes the transition
     */
  _transition(page, link) {
    page.el.addClass('active');
    link.addClass('active');
    this.events.transition.apply(this, [page, link]);
    this._afterTransition(page);
  }

  /*
        Finishes the transition
     */
  _afterTransition(page) {
    this.events.afterTransition.apply(this, [page]);
  }

  /*
        returns a page by name
     */
  getPage(name) {

    if (typeof name === 'string') {
      return this.pages.filter(function(element) {
        return element.name == name;
      })[0];
    } else if (typeof name === 'number') {
      return this.pages[name]; // will return a page at index x
    }

  }

  /*
        quick-validates if a page exists
     */
  exists(name) {
    return this.getPage(name) !== undefined;
  }

  /*
        public method for transitioning programatically
     */
  transition(name) {

    if (typeof name === 'number') {
      var name = this.getPage(name).name;
    }

    if (this.exists(name)) {
      this._beforeTransition(this.nav.children(`[href=${name}]`));
    } else {
      return false;
    }
  }

  // utility function that auto-snaps all the pageswitchers found in the document
  static findAndBind(selector = undefined) {

    if(selector) {
      // default page switcher init
      selector.each(function() {
        var switcher = new PageSwitcher({
          nav: $(this).find('.page-switcher__nav'),
          container: $(this).find('.page-switcher__pages')
        });
        $(this).data('pageSwitcher', switcher);
      });
    }

  }

}
