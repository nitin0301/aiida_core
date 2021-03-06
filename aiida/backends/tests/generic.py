# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida_core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""
Generic tests that need the use of the DB
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
from aiida.backends.testbase import AiidaTestCase
from aiida.common.exceptions import ModificationNotAllowed
from aiida import orm


class TestCode(AiidaTestCase):
    """
    Test the Code class.
    """

    def test_code_local(self):
        import tempfile

        from aiida.orm.code import Code
        from aiida.common.exceptions import ValidationError

        code = Code(local_executable='test.sh')
        with self.assertRaises(ValidationError):
            # No file with name test.sh
            code.store()

        with tempfile.NamedTemporaryFile(mode='w+') as fhandle:
            fhandle.write("#/bin/bash\n\necho test run\n")
            fhandle.flush()
            code.add_path(fhandle.name, 'test.sh')

        code.store()
        self.assertTrue(code.can_run_on(self.computer))
        self.assertTrue(code.get_local_executable(), 'test.sh')
        self.assertTrue(code.get_execname(), 'stest.sh')

    def test_remote(self):
        import tempfile

        from aiida.orm.code import Code
        from aiida.common.exceptions import ValidationError

        with self.assertRaises(ValueError):
            # remote_computer_exec has length 2 but is not a list or tuple
            _ = Code(remote_computer_exec='ab')

        # invalid code path
        with self.assertRaises(ValueError):
            _ = Code(remote_computer_exec=(self.computer, ''))

        # Relative path is invalid for remote code
        with self.assertRaises(ValueError):
            _ = Code(remote_computer_exec=(self.computer, 'subdir/run.exe'))

        # first argument should be a computer, not a string
        with self.assertRaises(TypeError):
            _ = Code(remote_computer_exec=('localhost', '/bin/ls'))

        code = Code(remote_computer_exec=(self.computer, '/bin/ls'))
        with tempfile.NamedTemporaryFile(mode='w+') as fhandle:
            fhandle.write("#/bin/bash\n\necho test run\n")
            fhandle.flush()
            code.add_path(fhandle.name, 'test.sh')

        with self.assertRaises(ValidationError):
            # There are files inside
            code.store()

        # If there are no files, I can store
        code.remove_path('test.sh')
        code.store()

        self.assertEquals(code.get_remote_computer().pk, self.computer.pk)
        self.assertEquals(code.get_remote_exec_path(), '/bin/ls')
        self.assertEquals(code.get_execname(), '/bin/ls')

        self.assertTrue(code.can_run_on(self.computer))
        othercomputer = orm.Computer(
            name='another_localhost',
            hostname='localhost',
            transport_type='local',
            scheduler_type='pbspro',
            workdir='/tmp/aiida').store()
        self.assertFalse(code.can_run_on(othercomputer))


class TestWfBasic(AiidaTestCase):
    """
    Tests for the workflows
    """

    def test_versioning_lowlevel(self):
        """
        Checks the versioning.
        """
        from aiida.workflows.test import WFTestEmpty

        w = WFTestEmpty().store()

        # Even if I stored many attributes, this should stay at 1
        self.assertEquals(w._dbworkflowinstance.nodeversion, 1)
        self.assertEquals(w.dbworkflowinstance.nodeversion, 1)
        self.assertEquals(w._dbworkflowinstance.nodeversion, 1)

        w.label = "label1"
        w.label = "label2"
        self.assertEquals(w._dbworkflowinstance.nodeversion, 3)
        self.assertEquals(w.dbworkflowinstance.nodeversion, 3)
        self.assertEquals(w._dbworkflowinstance.nodeversion, 3)

        w.description = "desc1"
        w.description = "desc2"
        w.description = "desc3"
        self.assertEquals(w._dbworkflowinstance.nodeversion, 6)
        self.assertEquals(w.dbworkflowinstance.nodeversion, 6)
        self.assertEquals(w._dbworkflowinstance.nodeversion, 6)


class TestGroupHashing(AiidaTestCase):

    def test_group_uuid_hashing_for_querybuidler(self):
        """
        QueryBuilder results should be reusable and shouldn't brake hashing.
        """
        from aiida.orm.group import Group
        from aiida.orm.querybuilder import QueryBuilder

        g = Group(name='test_group')
        g.store()

        # Search for the UUID of the stored group
        qb = QueryBuilder()
        qb.append(Group, project=['uuid'], filters={'name': {'==': 'test_group'}})
        [uuid] = qb.first()

        # Look the node with the previously returned UUID
        qb = QueryBuilder()
        qb.append(Group, project=['id'], filters={'uuid': {'==': uuid}})
        # Check that the query doesn't fail
        qb.all()
        # And that the results are correct
        self.assertEquals(qb.count(), 1)
        self.assertEquals(qb.first()[0], g.id)


class TestGroups(AiidaTestCase):
    """
    Test groups.
    """

    def test_creation(self):
        from aiida.orm.group import Group

        n = orm.Node()
        stored_n = orm.Node().store()

        with self.assertRaises(ValueError):
            # No name specified
            g = Group()

        g = Group(name='testgroup')

        with self.assertRaises(ValueError):
            # Too many parameters
            g = Group(name='testgroup', not_existing_kwarg=True)

        with self.assertRaises(ModificationNotAllowed):
            # g unstored
            g.add_nodes(n)

        with self.assertRaises(ModificationNotAllowed):
            # g unstored
            g.add_nodes(stored_n)

        g.store()

        with self.assertRaises(ValueError):
            # n unstored
            g.add_nodes(n)

        g.add_nodes(stored_n)

        nodes = list(g.nodes)
        self.assertEquals(len(nodes), 1)
        self.assertEquals(nodes[0].pk, stored_n.pk)

        # To avoid to find it in further tests
        g.delete()

    def test_description(self):
        """
        Test the update of the description both for stored and unstored
        groups.
        """
        from aiida.orm.group import Group

        n = orm.Node().store()

        g1 = Group(name='testgroupdescription1', description="g1").store()
        g1.add_nodes(n)

        g2 = Group(name='testgroupdescription2', description="g2")

        # Preliminary checks
        self.assertTrue(g1.is_stored)
        self.assertFalse(g2.is_stored)
        self.assertEquals(g1.description, "g1")
        self.assertEquals(g2.description, "g2")

        # Change
        g1.description = "new1"
        g2.description = "new2"

        # Test that the groups remained in their proper stored state and that
        # the description was updated
        self.assertTrue(g1.is_stored)
        self.assertFalse(g2.is_stored)
        self.assertEquals(g1.description, "new1")
        self.assertEquals(g2.description, "new2")

        # Store g2 and check that the description is OK
        g2.store()
        self.assertTrue(g2.is_stored)
        self.assertEquals(g2.description, "new2")

        # clean-up
        g1.delete()
        g2.delete()

    def test_add_nodes(self):
        """
        Test different ways of adding nodes
        """
        from aiida.orm.group import Group

        n1 = orm.Node().store()
        n2 = orm.Node().store()
        n3 = orm.Node().store()
        n4 = orm.Node().store()
        n5 = orm.Node().store()
        n6 = orm.Node().store()
        n7 = orm.Node().store()
        n8 = orm.Node().store()

        g = Group(name='test_adding_nodes')
        g.store()
        # Single node
        g.add_nodes(n1)
        # List of nodes
        g.add_nodes([n2, n3])
        # Single DbNode
        g.add_nodes(n4.dbnode)
        # List of DbNodes
        g.add_nodes([n5.dbnode, n6.dbnode])
        # List of orm.Nodes and DbNodes
        g.add_nodes([n7, n8.dbnode])

        # Check
        self.assertEquals(set([_.pk for _ in [n1, n2, n3, n4, n5, n6, n7, n8]]), set([_.pk for _ in g.nodes]))

        # Try to add a node that is already present: there should be no problem
        g.add_nodes(n1)
        self.assertEquals(set([_.pk for _ in [n1, n2, n3, n4, n5, n6, n7, n8]]), set([_.pk for _ in g.nodes]))

        # Cleanup
        g.delete()

    def test_remove_nodes(self):
        """
        Test node removal
        """
        from aiida.orm.group import Group

        n1 = orm.Node().store()
        n2 = orm.Node().store()
        n3 = orm.Node().store()
        n4 = orm.Node().store()
        n5 = orm.Node().store()
        n6 = orm.Node().store()
        n7 = orm.Node().store()
        n8 = orm.Node().store()
        n_out = orm.Node().store()

        g = Group(name='test_remove_nodes').store()

        # Add initial nodes
        g.add_nodes([n1, n2, n3, n4, n5, n6, n7, n8])
        # Check
        self.assertEquals(set([_.pk for _ in [n1, n2, n3, n4, n5, n6, n7, n8]]), set([_.pk for _ in g.nodes]))

        # Remove a node that is not in the group: nothing should happen
        # (same behavior of Django)
        g.remove_nodes(n_out)
        # Re-check
        self.assertEquals(set([_.pk for _ in [n1, n2, n3, n4, n5, n6, n7, n8]]), set([_.pk for _ in g.nodes]))

        # Remove one orm.Node and check
        g.remove_nodes(n4)
        self.assertEquals(set([_.pk for _ in [n1, n2, n3, n5, n6, n7, n8]]), set([_.pk for _ in g.nodes]))
        # Remove one DbNode and check
        g.remove_nodes(n7.dbnode)
        self.assertEquals(set([_.pk for _ in [n1, n2, n3, n5, n6, n8]]), set([_.pk for _ in g.nodes]))
        # Remove a list of Nodes and check
        g.remove_nodes([n1, n8])
        self.assertEquals(set([_.pk for _ in [n2, n3, n5, n6]]), set([_.pk for _ in g.nodes]))
        # Remove a list of Nodes and check
        g.remove_nodes([n1, n8])
        self.assertEquals(set([_.pk for _ in [n2, n3, n5, n6]]), set([_.pk for _ in g.nodes]))
        # Remove a list of DbNodes and check
        g.remove_nodes([n2.dbnode, n5.dbnode])
        self.assertEquals(set([_.pk for _ in [n3, n6]]), set([_.pk for _ in g.nodes]))

        # Remove a mixed list of orm.Nodes and DbNodes and check
        g.remove_nodes([n3, n6.dbnode])
        self.assertEquals(set(), set([_.pk for _ in g.nodes]))

        # Cleanup
        g.delete()

    def test_creation_from_dbgroup(self):
        from aiida.orm.group import Group

        n = orm.Node().store()

        g = Group(name='testgroup_from_dbgroup')
        g.store()
        g.add_nodes(n)

        dbgroup = g.dbgroup

        with self.assertRaises(ValueError):
            # Cannot pass more parameters, even if valid, if
            # dbgroup is specified
            Group(dbgroup=dbgroup, name="test")

        gcopy = Group(dbgroup=dbgroup)

        self.assertEquals(g.pk, gcopy.pk)
        self.assertEquals(g.uuid, gcopy.uuid)

        # To avoid to find it in further tests
        g.delete()

    def test_name_desc(self):
        from aiida.orm.group import Group

        g = Group(name='testgroup2', description='some desc')
        self.assertEquals(g.name, 'testgroup2')
        self.assertEquals(g.description, 'some desc')
        self.assertTrue(g.is_user_defined)
        g.store()
        # Same checks after storing
        self.assertEquals(g.name, 'testgroup2')
        self.assertTrue(g.is_user_defined)
        self.assertEquals(g.description, 'some desc')

        # To avoid to find it in further tests
        g.delete()

    def test_delete(self):
        from aiida.orm.group import Group
        from aiida.common.exceptions import NotExistent

        n = orm.Node().store()

        g = Group(name='testgroup3', description='some other desc')
        g.store()

        gcopy = Group.get(name='testgroup3')
        self.assertEquals(g.uuid, gcopy.uuid)

        g.add_nodes(n)
        self.assertEquals(len(g.nodes), 1)

        g.delete()

        with self.assertRaises(NotExistent):
            # The group does not exist anymore
            Group.get(name='testgroup3')

        # I should be able to restore it
        g.store()

        # Now, however, by deleting and recreating it, I lost the elements
        self.assertEquals(len(g.nodes), 0)
        self.assertEquals(g.name, 'testgroup3')
        self.assertEquals(g.description, 'some other desc')
        self.assertTrue(g.is_user_defined)

        # To avoid to find it in further tests
        g.delete()

    def test_rename(self):
        """
        Test the renaming of a Group
        """
        from aiida.orm.group import Group

        name_original = 'groupie'
        name_changed = 'nogroupie'

        g = Group(name=name_original, description='I will be renamed')

        # Check name changes work before storing
        self.assertEquals(g.name, name_original)
        g.name = name_changed
        self.assertEquals(g.name, name_changed)

        # Revert the name to its original and store it
        g.name = name_original
        g.store()

        # Check name changes work after storing
        self.assertEquals(g.name, name_original)
        g.name = name_changed
        self.assertEquals(g.name, name_changed)


class TestDbExtras(AiidaTestCase):
    """
    Test Extras
    """
    pass

    def test_replacement(self):
        pass


class TestBool(AiidaTestCase):

    def test_bool_conversion(self):
        from aiida.orm.data.bool import Bool
        for val in [True, False]:
            self.assertEqual(val, bool(Bool(val)))

    def test_int_conversion(self):
        from aiida.orm.data.bool import Bool
        for val in [True, False]:
            self.assertEqual(int(val), int(Bool(val)))
