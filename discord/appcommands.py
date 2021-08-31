import logging
import sys

from .enums import InteractionType


# Notable limitation: The current implementation generates commands where
# the subcommand group and subcommand, if present, are always the first two
# options.

# Also limitation: Currently only works with CHAT_INPUT commands,
# support for USER and MESSAGE commands TBD.

log = logging.getLogger(__name__)

INTERACTION_TYPE_APPLICATION_COMMAND = 2
COMMAND_TYPE_CHAT_INPUT = 1

OPT_TYPE_SUB_COMMAND = 1
OPT_TYPE_SUB_COMMAND_GROUP = 2
OPT_TYPE_STRING = 3
OPT_TYPE_INTEGER = 4
OPT_TYPE_BOOLEAN = 5
OPT_TYPE_USER = 6
OPT_TYPE_CHANNEL = 7
OPT_TYPE_ROLE = 8
OPT_TYPE_MENTIONABLE = 9
OPT_TYPE_NUMBER = 10


class CommandHandler:
  def __init__(self):
    self.handlers = {}  # map[(name, subcom_group, subcom) ->  CommandData]

  def add_command(self, data):
    k = data.to_key()
    if k in self.handlers:
      raise ValueError(F"Duplicate command registration for {k!r}")
    self.handlers[k] = data

  def remove_command(self, data):
    k = data.to_key()
    if k not in self.handlers:
      raise ValueError(F"Unmatched command unregistration for {k!r}")
    del self.handlers[k]

  def command(self, *args, **kwargs):
    def decorate(fn):
      d = CommandData(fn, *args, **kwargs)
      self.add_command(d)
      return fn
    return decorate

  def to_command_defs(self):
    return _build_command_defs(self.handlers.values())

  async def install_to_guild(self, client, guildid):
    defs = self.to_command_defs()
    await client.http.bulk_upsert_guild_commands(client.application_id, guildid, defs)


  async def handle(self, interaction):
    if not interaction.type == InteractionType.application_command:
      log.debug("Not handling interaction of non-appcommand type")
      return
    if not interaction.data:
      log.debug("Not handling interaction with missing data.")
      return
    if not interaction.data.get('type') == COMMAND_TYPE_CHAT_INPUT:
      log.debug("Not handling interaction of non-chatinput type")
      return

    try:
      name = interaction.data.get('name')
      subcommand_group = None
      subcommand = None
      options = interaction.data.get('options', [])
      if options and options[0].get('type') == OPT_TYPE_SUB_COMMAND_GROUP:
        subcommand_group = options[0].get('name')
        options = options[0].get('options', [])
      if options and options[0].get('type') == OPT_TYPE_SUB_COMMAND:
        subcommand = options[0].get('name')
        options = options[0].get('options', [])

      key = (name, subcommand_group, subcommand)
      handler = self.handlers.get(key)
      if not handler:
        log.warning(F"Interaction command not found for {key!r}")
        await interaction.response.send_message("Interaction code missing", ephemeral=True)
        return

      await handler.invoke(interaction, options)
    except:
      await self.handle_error(interaction, sys.exc_info())

  async def handle_error(self, interaction, exc_info):
    log.error("Interaction command handling failed", exc_info=exc_info)
    if issubclass(exc_info[0], CommandArgParseError):
      await interaction.response.send_message("Interaction code mismatch", ephemeral=True)
    elif not interaction.response.is_done():
      await interaction.response.send_message("Interaction code crashed", ephemeral=True)
    else:
      await interaction.followup.send(content="Interaction code crashed", ephemeral=True)


def _build_command_defs(handlers):
  # Implementation subtlety: We're hanging on to references to arrays
  # nested inside the command dicts, to insert additional subcommands
  # if we see more subcommands with the same name/group.
  existing_groups = {}
  existing_commands = {}
  result = []

  # It is vital that these helpers integrate the options reference as-is,
  # they must not copy it, or the later injection wouldn't work.
  def _format_command(h, options):
    return {
      'type': COMMAND_TYPE_CHAT_INPUT,
      'name': h.name,
      'description': h.description,
      'default_permission': h.roles_allowed is None,
      'options': options,
    }

  def _format_group(h, options):
    return {
      'type': OPT_TYPE_SUB_COMMAND_GROUP,
      'name': h.subcommand_group,
      'description': h.subcommand_group_description,
      'options': options,
    }

  def _format_subcommand(h, options):
    return {
      'type': OPT_TYPE_SUB_COMMAND,
      'name': h.subcommand,
      'description': h.subcommand_description,
      'options': options,
    }

  def _get_or_create_command(h):
    if opts := existing_commands.get(h.name):
      return opts
    opts = []
    existing_commands[h.name] = opts
    result.append(_format_command(h, opts))
    return opts

  def _get_or_create_group(h):
    if opts := existing_groups.get((h.name, h.subcommand_group)):
      return opts
    subopts = []
    existing_groups[(h.name, h.subcommand_group)] = subopts
    if h.subcommand_group is not None:
      opts = _get_or_create_command(h)
      opts.append(_format_group(h, subopts))
    else:
      result.append(_format_command(h, subopts))
    return subopts

  for h in handlers:
    if h.subcommand is not None:
      opts = _get_or_create_group(h)
      opts.append(_format_subcommand(h, h.opts_to_array()))
    elif h.subcommand_group is not None:
      opts = _get_or_create_command(h)
      opts.append(_format_group(h, h.opts_to_array()))
    else:
      result.append(_format_command(h, h.opts_to_array()))

  return result



class CommandData:
  def __init__(self, handler_fn, name, description,
               subcommand_group=None, subcommand_group_description=None,
               subcommand=None, subcommand_description=None,
               roles_allowed=None, roles_denied=None, options=None):
    self.handler_fn = handler_fn
    self.name = name
    self.description = description
    self.subcommand_group = subcommand_group
    self.subcommand_group_description = subcommand_group_description
    self.subcommand = subcommand
    self.subcommand_description = subcommand_description
    self.roles_allowed = roles_allowed
    self.roles_denied = roles_denied
    self.options = options or []

  def to_key(self):
    return (self.name, self.subcommand_group, self.subcommand)

  def opts_to_array(self):
    result = []
    for opt in self.options:
      result.append(opt.to_dict())

  async def invoke(self, interaction, options):
    cooked_options = self.parse_option_values(interaction, options)
    await self.handler_fn(interaction, *cooked_options)

  def parse_option_values(self, interaction, options):
    result = []
    idx = 0
    for expected in self.options:
      if idx >= len(options):
        satisfied = False
      else:
        found = options[idx]
        satisfied = (expected.name == found.get('name') and
                     expected.typecode == found.get('type'))

      if satisfied:
        converted = expected.parse(found.get('value'), interaction)
        if converted is None:
          raise CommandArgParseError(F"Option {expected.name} did not parse")
        result.append(converted)
        idx += 1
      else:
        if expected.required:
          raise CommandArgParseError(F"Option {expected.name} not found")
    if idx < len(options):
      raise CommandArgParseError(F"Option {options[idx].get('name')} not known")
    return result


class CommandArgParseError(RuntimeError):
  pass


class OptBase:
  def __init__(self, typecode, name, description, required=False):
    self.name = name
    self.description = description
    self.required = required
    self.typecode = typecode

  def to_dict(self):
    return {
      'type': self.typecode,
      'name': self.name,
      'description': self.description,
      'required': self.required,
    }

  def parse(self, value, interaction):
    raise NotImplementedError


class PlainOptBase:
  TYPECODE = None
  def __init__(self, *args, **kwargs):
    super().__init__(self.TYPECODE, *args, **kwargs)

  def parse(self, value, interaction):
    return value


class StringOpt(PlainOptBase):
  TYPECODE = OPT_TYPE_STRING

class IntOpt(PlainOptBase):
  TYPECODE = OPT_TYPE_INTEGER

class BoolOpt(PlainOptBase):
  TYPECODE = OPT_TYPE_BOOLEAN

class NumberOpt(PlainOptBase):
  TYPECODE = OPT_TYPE_NUMBER


class UserOpt(OptBase):
  def __init__(self, *args, **kwargs):
    super().__init__(OPT_TYPE_USER, *args, **kwargs)

  def parse(self, value, interaction):
    # TODO: Handle cache misses and non-guild messages
    return interaction.guild.get_member(value)


class ChannelOpt(OptBase):
  def __init__(self, *args, **kwargs):
    super().__init__(OPT_TYPE_CHANNEL, *args, **kwargs)

  def parse(self, value, interaction):
    return interaction.guild.get_channel(value)


class RoleOpt(OptBase):
  def __init__(self, *args, **kwargs):
    super().__init__(OPT_TYPE_ROLE, *args, **kwargs)

  def parse(self, value, interaction):
    return interaction.guild.get_role(value)


class MentionableOpt(OptBase):
  def __init__(self, *args, **kwargs):
    super().__init__(OPT_TYPE_MENTIONABLE, *args, **kwargs)

  def parse(self, value, interaction):
    return (interaction.guild.get_member(value) or
            interaction.guild.get_role(value))
