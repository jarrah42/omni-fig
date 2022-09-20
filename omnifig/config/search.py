from omnibelt import unspecified_argument


class ConfigSearchBase:
	def __init__(self, origin, queries, default=unspecified_argument, **kwargs):
		super().__init__(**kwargs)
		self.origin = origin
		self.queries = queries
		self.default = default
		self.result_node = None
		self.final_query = None

	class SearchFailed(KeyError):
		def __init__(self, queries):
			super().__init__(', '.join(queries))

	def _resolve_queries(self, src, queries):
		if not len(queries):
			return None, src
		for query in queries:
			if query is None:
				return None, src
			try:
				return query, src.get(query)
			except src.MissingKey:
				pass
		raise self.SearchFailed(queries)

	def find_node(self):
		try:
			self.final_query, self.result_node = self._resolve_queries(self.origin, self.queries)
		except self.SearchFailed:
			if self.default is self.origin.empty_default:
				raise
		return self.result_node

	def evaluate(self):
		self.find_node()
		self.product = self.package(self.result_node)
		return self.product

	def package(self, node):
		if node is None:
			return self.default
		return self.result_node.payload



class ConfigSearch(ConfigSearchBase):
	def __init__(self, origin, queries, default=unspecified_argument, silent=None,
	             ask_parent=True, lazy_iterator=None, parent_search=(), **kwargs):
		if silent is None:
			silent = origin.silent
		super().__init__(origin=origin, queries=queries, default=default, **kwargs)
		# self.init_origin = origin
		self.silent = silent
		self.query_chain = []
		self._ask_parent = ask_parent
		self.lazy_iterator = lazy_iterator
		self.remaining_queries = iter(queries)
		self.parent_search = parent_search

	_confidential_prefix = '_'

	def _resolve_query(self, src, query=None):
		try:
			result = src.get(query)
		except src.MissingKey:
			if self._ask_parent and not query.startswith(self._confidential_prefix):
				parent = src.parent
				if parent is not None:
					try:
						result = self._resolve_query(parent, query)
					except parent.MissingKey:
						pass
					else:
						self.query_chain.append(f'.{query}')
						return result
			self.query_chain.append(query)
			try:
				next_query = next(self.remaining_queries)
			except StopIteration:
				raise self.SearchFailed(f'No such key: {query!r}')
			else:
				return self._resolve_query(src, next_query)
		else:
			self.query_chain.append(query)
			return result

	def find_node(self):
		if self.queries is None or not len(self.queries):
			node = self.origin
		else:
			node = self._resolve_query(self.origin, *self.queries)
		# try:
		# 	node = self._resolve_query(self.origin, *self.queries)
		# except self.origin.MissingKey:
		# 	raise self.SearchFailed(self.queries)

		self.query_node = node
		self.result_node = self.process_node(node)
		return self.result_node

	# _weak_storage_prefix = '<?>'
	# _strong_storage_prefix = '<!>'
	reference_prefix = '<>'
	origin_reference_prefix = '<o>'

	def process_node(self, node: 'ConfigNode'):  # follows references
		if node.has_payload:
			payload = node.payload
			if isinstance(payload, str):
				if payload.startswith(self.reference_prefix):
					ref = payload[len(self.reference_prefix):]
					out = self._resolve_query(node, ref)
					return self.process_node(out)
				elif payload.startswith(self.origin_reference_prefix):
					ref = payload[len(self.origin_reference_prefix):]
					out = self._resolve_query(self.origin, ref)
					return self.process_node(out)
		return node

	def package_payload(self, node: 'ConfigNode'):  # creates components
		return node._create(search=self)

		if node.has_payload:
			payload = node.payload
			self.action = 'primitive'
			return payload

		# complex object - either component or list/dict
		try:
			cmpn, mods = node._extract_component_info()
		except node.NoComponentFound:
			# check for iterator
			if self.lazy_iterator is not None:
				self.action = 'iterator'
				node.reporter.search_report(self)
				return self.lazy_iterator(node)

			self.action = 'no-payload'
			node.reporter.search_report(self)

			# list or dict
			if isinstance(node, node.SparseNode):
				self.product_type = 'dict'
				product = OrderedDict()
				for key, child in node.children():
					product[key] = self.sub_search(node, key)

			elif isinstance(node, node.DenseNode):
				self.product_type = 'list'
				product = []
				for key, child in node.children():
					product.append(self.sub_search(node, key))

			else:
				raise TypeError(f'Unknown node type: {node!r}')

			return product
		else:
			# create component
			return node._create_component(cmpn, mods, record_key=node.reporter.get_key(self), silent=self.silent)

	def sub_search(self, node, key):
		return self.__class__(node, (key,), parent_search=(*self.parent_search, self),
		                      silent=self.silent).evaluate()

	def evaluate(self):
		try:
			node = self.find_node()
		except self.SearchFailed:
			if self.default is not self.origin.empty_default:
				return self.default
			raise
		else:
			self.product = self.package_payload(node)
			return self.product







