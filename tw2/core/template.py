import pkg_resources as pk, sys, core,  os
try:
    from dottedtemplatelookup import DottedTemplateLookup
    dotted_template_lookup = DottedTemplateLookup(input_encoding='utf-8', 
                                                       output_encoding='utf-8',
                                                       imports=[],
                                                       default_filters=[])
except ImportError:
    pass

class EngineError(core.WidgetError):
    "Errors inside ToscaWidgets, related to template engines."
    pass


rendering_extension_lookup = {'mako':'mak', 'genshi':'html', 'cheetah':'tmpl', 'kid':'kid'}
rm = pk.ResourceManager()

class EngineManager(dict):
    """Manages template engines. An instance is automatically created on each
    :class:`tw.core.TwMiddleware` instance. Users should not access
    this class directly.
    """
    def __init__(self, *args, **kw):
        super(EngineManager, self).__init__(self, *args, **kw)
        self._engine_name_cache = {}

    def render(self, template, displays_on, dct):
        """Render a template (passed in the form "engine_name:template_path")
        in a suitable way for inclusion in a template of the engine specified
        in ``displays_on``.
        """
        try:
            engine_name, template_path = template.split(':', 1)
        except ValueError:
            #if the engine name is not specified, find the best possible engine
            engine_name = self._get_engine_name(template)
            template_path = template
        
        if engine_name == 'genshi' and (template_path.startswith('/') or template_path[1] == ':'):
            engine_name = 'genshi_abs'

        if engine_name != 'cheetah':
            template = self[engine_name].load_template(template_path)

        adaptor_renderer = self._get_adaptor_renderer(engine_name, displays_on, template)

        if engine_name == 'mako':
            output = adaptor_renderer(**dct)
        else: 
            output = adaptor_renderer(template=template_path, info=dct)
        if isinstance(output, str):
            output = output.decode('utf-8')
        return output
    
    def _template_available(self, template_name, engine_name):
        ext = rendering_extension_lookup[engine_name]
        split = template_name.rsplit('.', 1)
        return os.path.isfile(rm.resource_filename(split[0], '.'.join((split[1], ext))))

    def _get_engine_name(self, template_name):
        try:
            return self._engine_name_cache[template_name]
        except KeyError:
            pass
        try:
            rl = core.request_local()
            pref_rend_eng = rl['middleware'].config.preferred_rendering_engines
        except (KeyError, AttributeError):
            pref_rend_eng = ['mako', 'genshi', 'cheetah', 'kid']
        #find the first file in the preffered engines that is available for templating
        for engine_name in pref_rend_eng:
            if self._template_available(template_name, engine_name):
                self._engine_name_cache[template_name] = engine_name
                return engine_name
        if not rl['middleware'].config.strict_engine_selection:
            pref_rend_eng = ['mako', 'genshi', 'cheetah', 'kid']
            for engine_name in pref_rend_eng:
                print engine_name
                if self._template_available(template_name, engine_name):
                    self._engine_name_cache[template_name] = engine_name
                    return engine_name
        raise EngineError("""Could not find template for: %s. 
You may need to specify a template engine name in the widget like mako:%s, or change the middleware
setup to include the template's templating language in your preferred_template_engines configuration.
As a last resort, you may set strict_template_selection to false which will grab whatever template
it finds if there one of your preferred template engines is not found."""%(template_name, template_name))
        
    def _get_adaptor_renderer(self, src, dst, template):
        """Return a function that will that processes a template appropriately,
        given the source and destination engine names.
        """
        if src == dst and src in ('kid', 'genshi'):
            return self[src].transform
        elif src == 'mako' and dst == 'kid':
            from kid import XML
            return lambda **kw: XML(template.render(**kw))
        elif src=='mako' and dst=='genshi':
            from genshi.core import Markup
            return lambda **kw: Markup(template.render(**kw))
        elif src == 'mako':
            return template.render
        elif src == 'kid' and dst == 'genshi':
            from genshi.input import ET
            return lambda **kw: ET(self[src].transform(**kw))
        elif dst == 'genshi':
            from genshi.core import Markup
            return lambda **kw: Markup(self[src].render(**kw))
        elif dst == 'kid':
            from kid import XML
            return lambda **kw: XML(self[src].render(**kw))
        else:
            return self[src].render

    def load_engine(self, name, options={}, extra_vars_func=None):
        if name in self:
            raise EngineError("Template engine '%s' is already loaded" % name)
        if name == 'mako':
            self[name] = dotted_template_lookup
            return self[name]

        orig_name = name
        if name == 'genshi_abs':
            name = 'genshi'
            options.update({'genshi.search_path': '/'})
        
        try:
            factory = core.request_local()['middleware'].config.available_rendering_engines[name]
        except (KeyError, AttributeError):
            for entrypoint in pk.iter_entry_points("python.templating.engines"):
                if entrypoint.name == name:
                    factory = entrypoint.load()
                    break
            else:
                raise EngineError("No template engine available for '%s'" % name)

        self[orig_name] = factory(extra_vars_func, options)

    def __getitem__(self, name):
        """Return a Buffet plugin by name. If the plugin is not loaded it
        will try to load it with default arguments.
        """
        try:
            return dict.__getitem__(self, name)
        except KeyError:
            self.load_engine(name)
            return dict.__getitem__(self, name)

global_engines = EngineManager()
